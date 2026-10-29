"""J05 discovery shared by fixture and explicit live search; no startup key read."""
from datetime import datetime
import html
import json
import os
import re
from threading import Lock
from time import monotonic
import unicodedata
from typing import Literal

import httpx2 as httpx
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from app.positions import diagnose_fen

OPENINGS = {
    'espagnole': 'ouverture espagnole', 'italienne': 'ouverture italienne',
    'sicilienne': 'défense sicilienne', 'francaise': 'défense française',
    'caro_kann': 'défense Caro-Kann', 'gambit_dame': 'gambit dame',
}
ENDPOINT = 'https://www.googleapis.com/youtube/v3/search'
MAX_BYTES = 65536
MAX_ITEMS = 50
ID_PATTERN = r'[A-Za-z0-9_-]{11}'

def youtube_key():
    # Only reached after explicit admitted live search. No startup/health lookup.
    return os.environ.get('YOUTUBE_API_KEY','')

class LiveSearchBudget:
    # Shared /search + /explore: 3 starts/60s, one in flight.
    # Counts failed attempts. No queue, waiting, retry or quota claim.
    def __init__(self,clock=monotonic):self.clock=clock;self.lock=Lock();self.starts=[];self.busy=False
    def enter(self):
        with self.lock:
            now=self.clock();self.starts=[t for t in self.starts if now-t<60]
            if self.busy:return 'YOUTUBE_LIVE_BUSY'
            if len(self.starts)>=3:return 'YOUTUBE_LOCAL_RATE_LIMITED'
            self.starts.append(now);self.busy=True
    def leave(self):
        with self.lock:self.busy=False
_LIVE_BUDGET=LiveSearchBudget()


class VideoRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    opening: Literal['espagnole', 'italienne', 'sicilienne', 'francaise', 'caro_kann', 'gambit_dame']
    context: str | None = Field(default=None, max_length=300)
    language: Literal['fr'] = 'fr'
    limit: StrictInt = Field(default=3, ge=1, le=3)
    fen: str | None = Field(default=None, min_length=1, max_length=256)

    @field_validator('context')
    @classmethod
    def clean_context(cls, value):
        if value is not None and any(ord(c) < 32 for c in value):
            raise ValueError('CONTROL_CHARACTERS')
        return value

    @field_validator('fen')
    @classmethod
    def validate_fen(cls, value):
        return diagnose_fen(value).fen_normalized if value is not None else None


class ControlledVideoQuery(BaseModel):
    """Plan interne fermé : aucun champ q libre, jamais exposé comme entrée HTTP."""
    model_config = ConfigDict(extra='forbid')
    opening: Literal['espagnole', 'italienne', 'sicilienne', 'francaise', 'caro_kann', 'gambit_dame']
    intent: Literal['understand_opening', 'understand_position', 'deepen_advice']
    topic: Literal['develop_minor_pieces', 'king_safety', 'central_control'] | None = None

    def render(self):
        base = OPENINGS[self.opening]
        if self.intent == 'understand_opening' and self.topic is None:
            return base + ' premiers coups idées objectifs ouverture échecs'
        if self.intent == 'understand_position' and self.topic == 'develop_minor_pieces':
            return base + ' plan de développement pièces mineures position ouverture échecs'
        if self.intent == 'deepen_advice' and self.topic is not None:
            theme = {'develop_minor_pieces': 'développement des pièces mineures',
                     'king_safety': 'sécurité du roi et préparation du roque',
                     'central_control': 'contrôle du centre par les pions'}[self.topic]
            return base + ' approfondir principe ' + theme + ' ouverture échecs'
        raise ValueError('INVALID_CONTROLLED_VIDEO_PLAN')


class Video(BaseModel):
    video_id: str
    title: str
    channel: str
    url: str | None
    thumbnail_url: str | None
    published_at: str | None = None


class VideoResult(BaseModel):
    status: Literal['ok', 'empty', 'disabled', 'unavailable']
    code: str | None = None
    source: Literal['youtube_data_api'] = 'youtube_data_api'
    source_mode: Literal['disabled', 'synthetic_fixture', 'live']
    synthetic: bool = True
    test_transport: bool = False
    editorial_review: Literal['not_reviewed'] = 'not_reviewed'
    opening: str
    query: str
    videos: list[Video] = Field(default_factory=list, max_length=3)
    filtered_items: int = 0
    truncated: bool = False


def plain_text(value, maximum):
    if not isinstance(value, str):
        raise ValueError('INVALID_METADATA')
    value = html.unescape(value).strip()
    if not value or len(value) > maximum or any(unicodedata.category(c) in ('Cc','Cf','Cs') or c in '<>' for c in value):
        raise ValueError('INVALID_METADATA')
    return value


def parse_video(item):
    if not isinstance(item, dict) or not isinstance(item.get('id'), dict) or item['id'].get('kind') != 'youtube#video':
        raise ValueError('NOT_VIDEO')
    ident = item['id'].get('videoId')
    if not isinstance(ident, str) or not re.fullmatch(ID_PATTERN, ident):
        raise ValueError('INVALID_VIDEO_ID')
    snippet = item.get('snippet')
    if not isinstance(snippet, dict):
        raise ValueError('INVALID_SNIPPET')
    title = plain_text(snippet.get('title'), 240)
    channel = plain_text(snippet.get('channelTitle'), 200)
    thumbnails = snippet.get('thumbnails', {})
    if not isinstance(thumbnails, dict):
        raise ValueError('INVALID_THUMBNAIL')
    thumbnail = None
    if 'default' in thumbnails:
        candidate = thumbnails['default']
        if not isinstance(candidate, dict):
            raise ValueError('INVALID_THUMBNAIL')
        thumbnail = candidate.get('url')
        if not isinstance(thumbnail, str) or not re.fullmatch(
                r'https://i\.ytimg\.com/vi/' + re.escape(ident) + r'/(?:default|mqdefault|hqdefault)\.jpg', thumbnail):
            raise ValueError('UNTRUSTED_THUMBNAIL')
    date = snippet.get('publishedAt')
    if date is not None:
        if not isinstance(date, str) or len(date) > 40:
            raise ValueError('INVALID_DATE')
        parsed = datetime.fromisoformat(date.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError('INVALID_DATE')
        date = parsed.isoformat()
    return Video(video_id=ident, title=title, channel=channel,
                 url='https://www.youtube.com/watch?v=' + ident,
                 thumbnail_url=thumbnail, published_at=date)


def synthetic_transport(request):
    # IDs inventés ; aucune existence de média n'est affirmée.
    query = request.url.params['q']
    indices = (2, 4, 5) if 'plan de développement' in query else (3, 6, 7) if 'approfondir principe' in query else (1, 2, 3)
    items = [{'id': {'kind': 'youtube#video', 'videoId': f'FIXTURE000{i}'},
              'snippet': {'title': f'EXEMPLE SYNTHÉTIQUE {i} — ouverture échecs',
                          'channelTitle': 'Chaîne synthétique de démonstration'}} for i in indices]
    return httpx.Response(200, json={'items': items[:int(request.url.params['maxResults'])]})


class VideoDiscovery:
    def __init__(self, mode='disabled', transport=None, *, key_lookup=None, live_budget=None):
        if mode not in ('disabled', 'synthetic_fixture', 'live'):
            raise ValueError('YOUTUBE_MODE_UNSUPPORTED_LIVE_NOT_IMPLEMENTED')
        if transport is not None and type(transport) is not httpx.MockTransport:
            raise ValueError('YOUTUBE_REQUIRES_MOCK_TRANSPORT_I01')
        self.mode = mode
        self.key_lookup=key_lookup or youtube_key
        self.live_budget=live_budget if live_budget is not None else _LIVE_BUDGET
        self.test_transport=transport is not None
        self.client = (httpx.Client(transport=transport or httpx.MockTransport(synthetic_transport))
                       if mode == 'synthetic_fixture' else httpx.Client(transport=transport,follow_redirects=False) if mode=='live' else None)

    @classmethod
    def from_env(cls, transport=None):
        # Configuration mode only; no secret read, connection or request at startup.
        return cls(os.getenv('YOUTUBE_MODE', 'disabled'), transport)

    def close(self):
        if self.client is not None:
            self.client.close()

    def search(self, request: VideoRequest):
        # Revalidation à la frontière de l'adaptateur, même hors route HTTP.
        request = VideoRequest.model_validate(request.model_dump())
        query = OPENINGS[request.opening] + ' explication ouverture échecs'
        return self._search_query(request, query)

    def search_plan(self, plan: ControlledVideoQuery):
        plan = ControlledVideoQuery.model_validate(plan.model_dump())
        query = plan.render()
        if len(query) > 240:
            raise ValueError('VIDEO_QUERY_TOO_LONG')
        return self._search_query(VideoRequest(opening=plan.opening, limit=3), query)

    def _search_query(self, request: VideoRequest, query: str):
        base = dict(source_mode=self.mode, synthetic=self.mode!='live', test_transport=self.test_transport, opening=request.opening, query=query)
        if self.client is None:
            return VideoResult(status='disabled', code='YOUTUBE_DISABLED', **base)
        params = {'part': 'snippet', 'type': 'video', 'q': query, 'maxResults': request.limit,
                  'safeSearch': 'strict', 'relevanceLanguage': request.language}
        key='';entered=False;headers={}
        if self.mode=='live':
            try:key=self.key_lookup()
            except Exception:return VideoResult(status='unavailable',code='YOUTUBE_KEY_UNAVAILABLE',**base)
            if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{10,256}',key):
                return VideoResult(status='unavailable',code='YOUTUBE_KEY_UNAVAILABLE',**base)
            code=self.live_budget.enter()
            if code:return VideoResult(status='unavailable',code=code,**base)
            entered=True;headers={'X-Goog-Api-Key':key}
        try:
            # One GET, exact HTTPS allowlist, no key in URL, retry or redirect.
            with self.client.stream('GET', ENDPOINT, params=params, headers=headers, timeout=5.0, follow_redirects=False) as response:
                body = bytearray()
                for chunk in response.iter_bytes():
                    if len(body) + len(chunk) > MAX_BYTES:
                        return VideoResult(status='unavailable', code='YOUTUBE_RESPONSE_TOO_LARGE', **base)
                    body.extend(chunk)
                if response.status_code != 200:
                    code = 'YOUTUBE_UPSTREAM_ERROR'
                    if response.status_code == 429:
                        code = 'YOUTUBE_RATE_LIMITED'
                    elif response.status_code in (401, 403):
                        code = 'YOUTUBE_AUTHORIZATION_FAILED'
                        try:
                            error = json.loads(body).get('error', {})
                            reasons = [r.get('reason') for r in error.get('errors', []) if isinstance(r, dict)]
                            if any(r in ('quotaExceeded', 'dailyLimitExceeded', 'rateLimitExceeded') for r in reasons):
                                code = 'YOUTUBE_QUOTA_EXCEEDED'
                        except (ValueError, AttributeError, TypeError):
                            pass
                    return VideoResult(status='unavailable', code=code, **base)
            if key and key.encode() in body:
                return VideoResult(status='unavailable',code='YOUTUBE_SENSITIVE_RESPONSE_REJECTED',**base)
            payload = json.loads(body)
            if key and key in json.dumps(payload,ensure_ascii=False):
                return VideoResult(status='unavailable',code='YOUTUBE_SENSITIVE_RESPONSE_REJECTED',**base)
            if not isinstance(payload, dict) or not isinstance(payload.get('items'), list):
                raise ValueError('INVALID_SCHEMA')
            if len(payload['items']) > MAX_ITEMS:
                raise ValueError('TOO_MANY_ITEMS')
        except httpx.TimeoutException:
            return VideoResult(status='unavailable', code='YOUTUBE_TIMEOUT', **base)
        except httpx.RequestError:
            return VideoResult(status='unavailable', code='YOUTUBE_TRANSPORT_ERROR', **base)
        except (ValueError, UnicodeError):
            return VideoResult(status='unavailable', code='YOUTUBE_INVALID_RESPONSE', **base)
        finally:
            if entered:self.live_budget.leave()
        videos = []; seen = set(); filtered = 0
        for item in payload['items']:
            try:
                video = parse_video(item)
            except (ValueError, TypeError, OverflowError):
                filtered += 1
                continue
            if key and key in video.model_dump_json():
                return VideoResult(status='unavailable',code='YOUTUBE_SENSITIVE_RESPONSE_REJECTED',**base)
            if video.video_id in seen:
                filtered += 1
                continue
            seen.add(video.video_id)
            # Fixtures remain linkless; only admitted live metadata gets a canonical URL.
            videos.append(video if self.mode=='live' else video.model_copy(update={'url': None, 'thumbnail_url': None}))
        return VideoResult(status='ok' if videos else 'empty', videos=videos[:request.limit],
                           filtered_items=filtered, truncated=len(videos) > request.limit, **base)

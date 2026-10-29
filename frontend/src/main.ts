import '@angular/compiler';
import {provideZonelessChangeDetection} from '@angular/core';
import {bootstrapApplication} from '@angular/platform-browser';
import {App} from './app';
import './style.css';
bootstrapApplication(App,{providers:[provideZonelessChangeDetection()]}).catch(()=>{document.body.textContent='Interface indisponible. Consultez la procédure locale.';});

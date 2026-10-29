// Runs only on a new Mongo volume, through the official initialization flow.
const password=process.env.MONGO_PASSWORD;
if(!/^[a-f0-9]{64}$/.test(password||''))throw new Error('MONGO_APP_PASSWORD_INVALID');
db.getSiblingDB('p13_sessions').createUser({user:'p13_sessions',pwd:password,roles:[{role:'readWrite',db:'p13_sessions'}]});

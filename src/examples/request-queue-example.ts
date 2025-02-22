import { RequestQueue } from '../services/RequestQueue';
import { RequestTask } from '../types/RequestTask';

const requestQueue = new RequestQueue();

// GETリクエストの追加
const getTask: RequestTask = {
    id: '1',
    type: 'GET',
    url: 'https://api.example.com/data',
    priority: 1,
    timestamp: Date.now()
};

// SENDリクエストの追加
const sendTask: RequestTask = {
    id: '2',
    type: 'SEND',
    url: 'https://api.example.com/data',
    payload: { data: 'example' },
    priority: 2,
    timestamp: Date.now()
};

requestQueue.enqueue(getTask);
requestQueue.enqueue(sendTask); 
export interface RequestTask {
    id: string;
    type: 'GET' | 'SEND';
    priority?: number;
    url: string;
    payload?: any;
    timestamp: number;
} 
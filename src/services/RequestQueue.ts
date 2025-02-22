import { RequestTask } from '../types/RequestTask';

export class RequestQueue {
    private queue: RequestTask[] = [];
    private isProcessing: boolean = false;

    // キューにタスクを追加
    public enqueue(task: RequestTask): void {
        this.queue.push(task);
        this.queue.sort((a, b) => {
            // 優先順位で並び替え（高い順）
            if (a.priority !== b.priority) {
                return (b.priority || 0) - (a.priority || 0);
            }
            // 同じ優先順位の場合はタイムスタンプ順
            return a.timestamp - b.timestamp;
        });

        if (!this.isProcessing) {
            this.processQueue();
        }
    }

    // キューの処理
    private async processQueue(): Promise<void> {
        if (this.queue.length === 0) {
            this.isProcessing = false;
            return;
        }

        this.isProcessing = true;
        const task = this.queue.shift();

        try {
            if (task) {
                await this.executeTask(task);
            }
        } catch (error) {
            console.error(`Error processing task ${task?.id}:`, error);
        }

        // 次のタスクを処理
        this.processQueue();
    }

    // タスクの実行
    private async executeTask(task: RequestTask): Promise<void> {
        const options: RequestInit = {
            method: task.type,
            headers: {
                'Content-Type': 'application/json',
            },
        };

        if (task.type === 'SEND' && task.payload) {
            options.body = JSON.stringify(task.payload);
        }

        await fetch(task.url, options);
    }
} 
-- 005_task_table.sql — Phase 11 T4：异步任务表（D4；C2 裁决载体）
-- BackgroundTasks 单进程 uvicorn 够用（C2 否决 celery/rq：新依赖+broker
-- 运维 YAGNI；否决纯内存：deletion_code 一次性展示语义须跨重启持久）。
-- 状态机：pending → running → completed | failed（D4：失败 error 明示不静默）。
CREATE TABLE IF NOT EXISTS task (
    id         uuid PRIMARY KEY,
    kind       text NOT NULL,
    status     text NOT NULL DEFAULT 'pending'
               CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    result     jsonb,
    error      text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

/**
 * 产品使用 AI 助手（2026-09-15 三端，web 端）：
 * 右下角悬浮球（错开「?」引导球：insetBlockEnd 96 vs 默认 40）+ Drawer 聊天。
 * 会话仅本地 state，后端无状态不落库；只答产品使用问题。
 */
import { useRef, useState } from 'react';
import { Button, Drawer, FloatButton, Input, Spin, Tag } from 'antd';
import { RobotOutlined, SendOutlined } from '@ant-design/icons';
import { assistantAPI } from '../../services/assistant';

interface Bubble {
  role: 'user' | 'assistant';
  content: string;
}

const GREETING: Bubble = {
  role: 'assistant',
  content:
    '你好，我是产品使用助手。不知道某个功能在哪、或者怎么用，直接问我，比如「待审的资质在哪看？」「怎么给专员同步知识库？」',
};

const SUGGESTIONS = [
  '待审的资质在哪看？',
  '怎么冻结违规分身？',
  '对话检索支持什么条件？',
  'AI 出题怎么用？',
];

export default function AssistantChat() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Bubble[]>([GREETING]);
  const [input, setInput] = useState('');
  const [asking, setAsking] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  const ask = async (text?: string) => {
    const question = (text ?? input).trim();
    if (!question || asking) return;
    setMessages((prev) => [...prev, { role: 'user', content: question }]);
    setInput('');
    setAsking(true);
    try {
      const res = await assistantAPI.ask(question);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: res.data?.data?.answer || '抱歉，没能生成回答，请换个问法试试。' },
      ]);
    } catch (e: any) {
      // client.ts 拦截器已弹错误提示，这里补一条气泡保持会话连续
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: e?.response?.data?.message || '网络异常，请稍后重试。' },
      ]);
    } finally {
      setAsking(false);
      requestAnimationFrame(() => {
        listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
      });
    }
  };

  return (
    <>
      {/* data-tour 不占用（help-btn 是引导定位器）；错开右下角「?」引导球 */}
      <FloatButton
        icon={<RobotOutlined />}
        tooltip="AI 助手"
        onClick={() => setOpen(true)}
        style={{ insetBlockEnd: 96 }}
        data-testid="assistant-fab"
      />
      <Drawer
        title={
          <span>
            <RobotOutlined style={{ marginRight: 8 }} />
            AI 助手 · 产品使用问答
          </span>
        }
        placement="right"
        width={420}
        open={open}
        onClose={() => setOpen(false)}
        styles={{ body: { display: 'flex', flexDirection: 'column', padding: 12, height: '100%' } }}
      >
        <div
          ref={listRef}
          style={{ flex: 1, overflowY: 'auto', padding: '8px 4px' }}
        >
          {messages.map((m, i) => (
            <div
              key={i}
              style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start', marginBottom: 12 }}
            >
              <div
                style={{
                  maxWidth: '85%',
                  padding: '8px 12px',
                  borderRadius: 12,
                  background: m.role === 'user' ? '#1677ff' : '#f5f5f5',
                  color: m.role === 'user' ? '#fff' : 'rgba(0,0,0,0.88)',
                  fontSize: 13,
                  lineHeight: '20px',
                  whiteSpace: 'pre-wrap',
                }}
              >
                {m.content}
              </div>
            </div>
          ))}
          {asking && (
            <div style={{ display: 'flex', marginBottom: 12 }}>
              <div style={{ padding: '8px 12px', borderRadius: 12, background: '#f5f5f5' }}>
                <Spin size="small" />
              </div>
            </div>
          )}
        </div>

        {messages.length === 1 && !asking && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, padding: '4px 0 8px' }}>
            {SUGGESTIONS.map((s) => (
              <Tag key={s} style={{ cursor: 'pointer', marginInlineEnd: 0 }} onClick={() => ask(s)}>
                {s}
              </Tag>
            ))}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, paddingTop: 8, borderTop: '1px solid #f0f0f0' }}>
          <Input.TextArea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="问问功能在哪、怎么用…"
            autoSize={{ minRows: 1, maxRows: 4 }}
            maxLength={500}
            onPressEnter={(e) => {
              if (!e.shiftKey) {
                e.preventDefault();
                ask();
              }
            }}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            loading={asking}
            disabled={!input.trim()}
            onClick={() => ask()}
          />
        </div>
      </Drawer>
    </>
  );
}

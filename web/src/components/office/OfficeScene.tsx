import { useEffect, useState } from 'react';
import { Button, Empty } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import Workstation from './Workstation';
import type { LiveStatusItem } from '../../types';

const CSS = `
.office-scene { position: relative; background: linear-gradient(180deg, #eef4fb 0%, #f7f9fc 72%, #e8e4dc 72%, #e8e4dc 100%);
  border: 1px solid #eaeaea; border-radius: 12px; padding: 42px 24px 18px; min-height: 320px; overflow: hidden; }
.office-window { position: absolute; top: 18px; width: 90px; height: 62px; border-radius: 6px;
  background: linear-gradient(180deg, #cfe8ff 0%, #e8f4ff 100%); border: 3px solid #ffffff; box-shadow: 0 0 0 1px #dfe6ee; overflow: hidden; }
.office-window::before { content: ''; position: absolute; left: 0; right: 0; top: 28px; height: 3px; background: #dfe6ee; }
.office-window::after { content: ''; position: absolute; top: 0; bottom: 0; left: 42px; width: 3px; background: #dfe6ee; }
.office-cloud { position: absolute; background: #ffffff; border-radius: 12px; opacity: 0.85; }
.office-clock { position: absolute; top: 12px; right: 24px; width: 54px; height: 54px; border-radius: 50%;
  background: #fff; border: 2px solid #d9d9d9; box-shadow: 0 2px 6px rgba(0,0,0,.08); }
.office-plant { position: absolute; bottom: 18px; }
.office-row { display: flex; flex-wrap: wrap; justify-content: center; gap: 22px; position: relative; z-index: 2; padding-top: 10px; }
`;

/** 墙钟：按当前时间转指针 */
function WallClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = window.setInterval(() => setNow(new Date()), 30000);
    return () => window.clearInterval(t);
  }, []);
  const h = (now.getHours() % 12) * 30 + now.getMinutes() * 0.5;
  const m = now.getMinutes() * 6;
  return (
    <div className="office-clock">
      <svg viewBox="0 0 54 54" style={{ display: 'block' }}>
        {[0, 30, 60, 90].map((a) => (
          <line key={a} x1="27" y1="5" x2="27" y2="9" stroke="#8c8c8c" strokeWidth="2"
            transform={`rotate(${a} 27 27)`} />
        ))}
        <line x1="27" y1="27" x2="27" y2="16" stroke="#333" strokeWidth="2.6" strokeLinecap="round"
          transform={`rotate(${h} 27 27)`} />
        <line x1="27" y1="27" x2="27" y2="12" stroke="#1677ff" strokeWidth="1.6" strokeLinecap="round"
          transform={`rotate(${m} 27 27)`} />
        <circle cx="27" cy="27" r="2" fill="#333" />
      </svg>
    </div>
  );
}

/** 办公室场景：墙/窗/云/墙钟/绿植 + 工位排布（每排最多 5 个，超出换行） */
export default function OfficeScene({
  items, onAdd, onEdit, onToggleStatus, onViewData,
}: {
  items: LiveStatusItem[];
  onAdd: () => void;
  onEdit: (item: LiveStatusItem) => void;
  onToggleStatus: (item: LiveStatusItem) => void;
  onViewData: (item: LiveStatusItem) => void;
}) {
  return (
    <div className="office-scene">
      <style>{CSS}</style>
      {/* 装饰：两扇窗 + 云 + 墙钟 + 绿植 */}
      <div className="office-window" style={{ left: 24 }} />
      <div className="office-window" style={{ left: 132, top: 26 }} />
      <div className="office-cloud" style={{ left: 40, top: 10, width: 34, height: 12 }} />
      <div className="office-cloud" style={{ left: 205, top: 8, width: 26, height: 9 }} />
      <WallClock />
      <svg className="office-plant" viewBox="0 0 60 56" width="56" style={{ right: 24 }}>
        <path d="M30 20 Q20 4 8 8 Q16 14 30 20 Z" fill="#7cae6a" />
        <path d="M30 20 Q40 2 52 6 Q44 14 30 20 Z" fill="#6fa35c" />
        <path d="M30 22 Q30 6 30 2 Q32 8 32 14 Z" fill="#5c8f4a" />
        <path d="M30 20 Q28 40 30 56 Q32 40 30 20 Z" fill="#8a5a33" />
      </svg>
      {items.length === 0 ? (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 300 }}>
          <Empty description="暂无数字专员">
            <Button type="primary" icon={<PlusOutlined />} onClick={onAdd}>新增专员</Button>
          </Empty>
        </div>
      ) : (
        <div className="office-row">
          {items.map((item, index) => (
            <Workstation
              key={item.id}
              item={item}
              index={index}
              onEdit={onEdit}
              onToggleStatus={onToggleStatus}
              onViewData={onViewData}
            />
          ))}
        </div>
      )}
    </div>
  );
}

import { Fragment } from 'react';
import { Button, Empty } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import Workstation from './Workstation';
import type { LiveStatusItem } from '../../types';

const PER_ROW = 6;

const CSS = `
.office-scene { position: relative; perspective: 900px; background: #0b1220; border-radius: 12px;
  padding: 20px; min-height: 360px; overflow: hidden; }
.office-floor { position: relative; min-height: 320px; transform: rotateX(18deg); transform-style: preserve-3d;
  background:
    linear-gradient(90deg, rgba(88, 166, 255, 0.13) 1px, transparent 1px),
    linear-gradient(0deg, rgba(88, 166, 255, 0.13) 1px, transparent 1px),
    linear-gradient(180deg, #101828 0%, #1d2a3d 100%);
  background-size: 26px 26px, 26px 26px, 100% 100%;
  border: 1px solid rgba(88, 166, 255, 0.35); border-radius: 10px; }
.office-rows { position: relative; z-index: 2; display: flex; flex-direction: column; align-items: center;
  gap: 18px; transform-style: preserve-3d; padding: 46px 18px 26px; }
.office-row { display: flex; flex-wrap: wrap; justify-content: center; gap: 38px; transform-style: preserve-3d; }
.office-aisle { width: calc(100% - 24px); height: 10px; display: flex; align-items: center; justify-content: center; }
.office-aisle::before { content: ''; width: 100%; height: 1px; background: rgba(88, 166, 255, 0.55);
  box-shadow: 0 0 8px rgba(88, 166, 255, 0.6); }
.office-empty { position: relative; z-index: 2; display: flex; justify-content: center; align-items: center; height: 320px; }
.office-empty .ant-empty-description { color: #8fa3bf; }
`;

/** 3D 俯视蓝图办公室：perspective + 地板 rotateX(18°)，工位 billboard 反旋转直立；每排 6 个，排间浅蓝发光过道线 */
export default function OfficeScene({
  items, onAdd, onEdit, onToggleStatus, onViewData,
}: {
  items: LiveStatusItem[];
  onAdd: () => void;
  onEdit: (item: LiveStatusItem) => void;
  onToggleStatus: (item: LiveStatusItem) => void;
  onViewData: (item: LiveStatusItem) => void;
}) {
  const rows: LiveStatusItem[][] = [];
  for (let i = 0; i < items.length; i += PER_ROW) rows.push(items.slice(i, i + PER_ROW));

  return (
    <div className="office-scene">
      <style>{CSS}</style>
      {items.length === 0 ? (
        <div className="office-empty">
          <Empty description="暂无数字专员">
            <Button type="primary" icon={<PlusOutlined />} onClick={onAdd}>新增专员</Button>
          </Empty>
        </div>
      ) : (
        <div className="office-floor">
          <div className="office-rows">
            {rows.map((row, ri) => (
              <Fragment key={ri}>
                {ri > 0 && <div className="office-aisle" />}
                <div className="office-row">
                  {row.map((item, index) => (
                    <Workstation
                      key={item.id}
                      item={item}
                      index={index + ri * PER_ROW}
                      onEdit={onEdit}
                      onToggleStatus={onToggleStatus}
                      onViewData={onViewData}
                    />
                  ))}
                </div>
              </Fragment>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

import { ProFormText, ProFormSelect, ProFormTextArea } from '@ant-design/pro-components';

/**
 * 专员创建/编辑表单 —— 字段与后端 specialists.py 白名单对齐：
 * name / product_id / bailian_app_id / compliance_level / status / persona / knowledge_scope
 * （style/description/app_id 等后端不存在的字段一律不发）
 */
export default function SpecialistForm() {
  return (
    <>
      <ProFormText name="name" label="专员名称" rules={[{ required: true, message: '请输入专员名称' }]} />
      <ProFormText
        name="product_id"
        label="关联产品 ID"
        rules={[{ required: true, message: '请输入产品 ID' }]}
        placeholder="对应产品表的数字 ID"
        fieldProps={{ type: 'number' }}
      />
      <ProFormText
        name="bailian_app_id"
        label="百炼 App ID"
        placeholder="mm_xxx（不填则不可对话，可后续补配）"
      />
      <ProFormSelect
        name="compliance_level"
        label="合规级别"
        placeholder="默认内部使用"
        options={[
          { label: '内部使用', value: 'internal' },
          { label: '低风险', value: 'low' },
          { label: '中风险', value: 'medium' },
          { label: '高风险', value: 'high' },
        ]}
      />
      <ProFormSelect
        name="status"
        label="状态"
        placeholder="默认草稿"
        options={[
          { label: '草稿', value: 'draft' },
          { label: '正式', value: 'active' },
          { label: '停用', value: 'disabled' },
        ]}
      />
      <ProFormTextArea name="persona" label="人设（可选，JSON）" placeholder='如 {"style":"专业严谨"}' />
      <ProFormTextArea name="knowledge_scope" label="知识范围（可选，JSON）" placeholder='如 ["肺癌","乳腺癌"]' />
    </>
  );
}

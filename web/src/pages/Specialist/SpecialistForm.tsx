import { ProFormText, ProFormSelect, ProFormTextArea } from '@ant-design/pro-components';

export default function SpecialistForm() {
  return (
    <>
      <ProFormText name="name" label="专员名称" rules={[{ required: true, message: '请输入' }]} />
      <ProFormText name="product" label="关联产品" rules={[{ required: true }]} />
      <ProFormText name="app_id" label="百炼 App ID" rules={[{ required: true }]} placeholder="mm_xxx" />
      <ProFormSelect name="status" label="状态"
        options={[
          { label: '草稿', value: 'draft' }, { label: '实习', value: 'intern' },
          { label: '正式', value: 'active' }, { label: '停用', value: 'disabled' },
        ]} />
      <ProFormSelect name="style" label="沟通风格"
        options={[
          { label: '专业严谨', value: 'professional' }, { label: '亲和友善', value: 'friendly' },
          { label: '学术深度', value: 'academic' },
        ]} />
      <ProFormTextArea name="description" label="能力描述" placeholder="该专员擅长..." />
    </>
  );
}

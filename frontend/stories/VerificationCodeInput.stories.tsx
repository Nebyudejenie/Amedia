import { VerificationCodeInput } from '@/components/forms/VerificationCodeInput';

const meta = {
  title: 'Forms/VerificationCodeInput',
  component: VerificationCodeInput,
};
export default meta;

export const Empty = { args: { value: '', onChange: () => {} } };
export const Partial = { args: { value: '123', onChange: () => {} } };
export const WithError = { args: { value: '', onChange: () => {}, error: 'Invalid code' } };

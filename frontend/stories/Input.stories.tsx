import { Input } from '@/components/ui/Input';

const meta = {
  title: 'UI/Input',
  component: Input,
};
export default meta;

export const Default = { args: { label: 'Email', placeholder: 'you@example.com' } };
export const WithError = {
  args: { label: 'Email', defaultValue: 'not-an-email', error: 'Enter a valid email' },
};
export const Password = {
  args: { label: 'Password', showPasswordToggle: true, defaultValue: 'hunter2hunter2' },
};
export const Disabled = { args: { label: 'Email', value: 'locked@example.com', disabled: true } };

import { Button } from '@/components/ui/Button';

const meta = {
  title: 'UI/Button',
  component: Button,
};
export default meta;

export const Primary = { args: { children: 'Save changes', variant: 'primary' } };
export const Secondary = { args: { children: 'Cancel', variant: 'secondary' } };
export const Danger = { args: { children: 'Delete', variant: 'danger' } };
export const Loading = { args: { children: 'Saving…', isLoading: true } };
export const Disabled = { args: { children: 'Unavailable', disabled: true } };

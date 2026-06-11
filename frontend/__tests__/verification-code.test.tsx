import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { VerificationCodeInput } from '@/components/forms/VerificationCodeInput';

function Wrapper({ onChange = () => {} }: { onChange?: (code: string) => void }) {
  // Controlled wrapper mirroring real usage
  const [value, setValue] = (require('react') as typeof import('react')).useState('');
  return (
    <VerificationCodeInput
      value={value}
      onChange={(code) => {
        setValue(code);
        onChange(code);
      }}
    />
  );
}

describe('VerificationCodeInput', () => {
  it('renders six digit inputs', () => {
    render(<VerificationCodeInput value="" onChange={() => {}} />);
    expect(screen.getAllByRole('textbox')).toHaveLength(6);
  });

  it('auto-advances focus as digits are typed', async () => {
    const user = userEvent.setup();
    render(<Wrapper />);

    const inputs = screen.getAllByRole('textbox');
    await user.click(inputs[0]!);
    await user.keyboard('1');
    expect(inputs[1]).toHaveFocus();
    await user.keyboard('2');
    expect(inputs[2]).toHaveFocus();
  });

  it('collects the full code', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Wrapper onChange={onChange} />);

    await user.click(screen.getAllByRole('textbox')[0]!);
    await user.keyboard('123456');

    expect(onChange).toHaveBeenLastCalledWith('123456');
  });

  it('ignores non-digit characters', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Wrapper onChange={onChange} />);

    await user.click(screen.getAllByRole('textbox')[0]!);
    await user.keyboard('a');
    expect(onChange).not.toHaveBeenCalledWith('a');
  });

  it('moves focus back on backspace from an empty digit', async () => {
    const user = userEvent.setup();
    render(<Wrapper />);

    const inputs = screen.getAllByRole('textbox');
    await user.click(inputs[0]!);
    await user.keyboard('1');
    expect(inputs[1]).toHaveFocus();
    await user.keyboard('{Backspace}');
    expect(inputs[0]).toHaveFocus();
  });

  it('shows error text', () => {
    render(<VerificationCodeInput value="" onChange={() => {}} error="Invalid code" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Invalid code');
  });
});

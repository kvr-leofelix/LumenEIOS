import React, { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { Modal } from '../components/common/Modal';

const Host = () => {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button onClick={() => setOpen(true)}>Open it</button>
      <Modal isOpen={open} onClose={() => setOpen(false)} title="Dialog title" footer={<button>Save</button>}>
        <input aria-label="First field" />
      </Modal>
    </div>
  );
};

describe('Modal keyboard accessibility', () => {
  it('moves focus into the dialog, traps Tab, closes on Escape and restores focus to the trigger', () => {
    render(<Host />);
    const trigger = screen.getByRole('button', { name: 'Open it' });
    trigger.focus();
    fireEvent.click(trigger);
    const dialog = screen.getByRole('dialog');
    expect(dialog.contains(document.activeElement)).toBe(true);

    const save = screen.getByRole('button', { name: 'Save' });
    save.focus();
    fireEvent.keyDown(window, { key: 'Tab' }); // last focusable -> wraps to first
    expect(dialog.contains(document.activeElement)).toBe(true);
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Close dialog' }));

    fireEvent.keyDown(window, { key: 'Tab', shiftKey: true }); // first -> wraps to last
    expect(document.activeElement).toBe(save);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});

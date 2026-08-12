import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DetailSlideOver } from './drawer/DetailSlideOver';
import { MessageItem } from './chat/MessageItem';

describe('metrics-only observability', () => {
  it('keeps the completed answer usable when trace is unavailable', () => {
    render(<MessageItem onOpenDetails={vi.fn()} message={{
      id: 'assistant', sender: 'assistant', content: 'Đã có kết quả.', timestamp: '10:30', traceStatus: 'unavailable',
    }} />);
    expect(screen.getByText('Đã có kết quả.')).toBeInTheDocument();
    expect(screen.getByText('Trace unavailable')).toBeInTheDocument();
  });

  it('drawer exposes results, map, and safe trace only', () => {
    render(<DetailSlideOver merchantId="94" onClose={vi.fn()} message={{
      id: 'assistant', sender: 'assistant', content: 'Kết quả', timestamp: '10:31', analyzedMerchants: [], traceStatus: 'processing',
    }} />);
    expect(screen.getByRole('tab', { name: 'Trace' })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: /Tools/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Trace' }));
    expect(screen.getByText('Trace is processing')).toBeInTheDocument();
  });
});

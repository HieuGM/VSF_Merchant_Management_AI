import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatbotPage } from './ChatbotPage';

const mocks = vi.hoisted(() => ({
  sendMessage: vi.fn(),
  createNewSession: vi.fn(),
  useMerchantChat: vi.fn(),
  fetchMerchantProfile: vi.fn(),
  fetchDemoTargetMerchants: vi.fn(),
}));

vi.mock('../hooks/useMerchantChat', () => ({
  useMerchantChat: mocks.useMerchantChat,
}));

vi.mock('../api/merchantProfileApi', () => ({
  fetchMerchantProfile: mocks.fetchMerchantProfile,
  fetchDemoTargetMerchants: mocks.fetchDemoTargetMerchants,
}));

describe('ChatbotPage', () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mocks.useMerchantChat.mockReturnValue({
      messages: [],
      sessions: [],
      isThinking: false,
      sendMessage: mocks.sendMessage,
      switchSession: vi.fn(),
      createNewSession: mocks.createNewSession,
      deleteSession: vi.fn(),
      activeSessionId: 'sess-test',
    });
    mocks.fetchMerchantProfile.mockResolvedValue({
      merchant_id: '68814',
      metadata: { name: 'Dì Bảy - Bún Mắm & Bún Bò Huế' },
    });
    mocks.fetchDemoTargetMerchants.mockResolvedValue([
      {
        merchant_id: '68814',
        name: 'Dì Bảy - Bún Mắm & Bún Bò Huế',
        city: 'TP. HCM',
        cuisine: 'Món Việt',
      },
      {
        merchant_id: '233150',
        name: 'Sushi Lounge - Thống Nhất',
        city: 'Vũng Tàu',
        cuisine: 'Món Nhật, Món Á',
      },
    ]);
  });

  it('connects the responsive shell to chat actions', async () => {
    render(<ChatbotPage />);
    expect(await screen.findByRole('button', { name: 'Mở điều hướng' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Tin nhắn cho AI Advisor'), { target: { value: 'Phân tích cửa hàng' } });
    fireEvent.click(screen.getByRole('button', { name: 'Gửi tin nhắn' }));
    expect(mocks.sendMessage).toHaveBeenCalledWith('Phân tích cửa hàng');
    fireEvent.click(screen.getByRole('button', { name: 'Cuộc trò chuyện mới' }));
    expect(mocks.createNewSession).toHaveBeenCalledOnce();
  });

  it('uses only database demo targets and replaces a stale merchant id', async () => {
    localStorage.setItem('merchant_dev_context', '94');

    render(<ChatbotPage />);

    const selector = await screen.findByLabelText('Chọn Merchant');
    expect([...selector.querySelectorAll('option')].map((option) => option.value)).toEqual([
      '68814',
      '233150',
    ]);
    expect(screen.queryByRole('option', { name: /Green Life Poke/i })).not.toBeInTheDocument();
    await waitFor(() => {
      expect(mocks.useMerchantChat).toHaveBeenLastCalledWith('68814');
      expect(localStorage.getItem('merchant_dev_context')).toBe('68814');
    });
  });
});

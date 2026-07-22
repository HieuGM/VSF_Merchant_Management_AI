import React from 'react';
import { CompetitorItem, DimensionHighlight } from '../../types/merchantChat';
import { SVGIcon } from '../common/SVGIcon';

interface DetailSlideOverProps {
  item: CompetitorItem | null;
  onClose: () => void;
  onAskAgent: (query: string) => void;
}

const DEFAULT_DIMENSIONS: DimensionHighlight[] = [
  { dimension: '1. Giá cả & Giá trị', score: 8.2, comparisonNote: 'Thấp hơn quán bạn 5-10%, thuộc phân khúc bình dân.' },
  { dimension: '2. Chất lượng món ăn', score: 8.8, comparisonNote: 'Khách hàng khen ngợi vị đậm đà truyền thống.' },
  { dimension: '3. Tốc độ giao hàng', score: 9.0, comparisonNote: 'Thời gian chuẩn bị món trung bình 8 phút.' },
  { dimension: '4. Đóng gói & Bao bì', score: 7.5, comparisonNote: 'Bao bì nhựa cơ bản, chưa có túi giữ nhiệt chuyên dụng.' },
  { dimension: '5. Thái độ phục vụ', score: 8.5, comparisonNote: 'Xử lý khiếu nại nhanh chóng, đánh giá tích cực.' },
  { dimension: '6. Chương trình khuyến mãi', score: 9.1, comparisonNote: 'Áp dụng mã FS15K liên tục giờ cao điểm.' },
  { dimension: '7. Khoảng cách & Vị trí', score: 8.0, comparisonNote: 'Cùng bán kính giao hàng 2km khu vực trung tâm.' },
  { dimension: '8. Hài lòng tổng quan', score: 8.6, comparisonNote: 'Lượng khách trung thành đạt 64% trên ứng dụng.' },
];

const DEFAULT_QUOTES = [
  '[REV-104] Món ăn vị hủ tiếu truyền thống đậm đà, giao đúng giờ nhưng suất ăn hơi ít so với giá tiền.',
  '[REV-112] Quán rất đông giờ cao điểm, khuyến mãi giảm 20% thu hút nhiều đơn hàng trên ứng dụng.',
  '[REV-205] Bao bì đóng gói cẩn thận, nước lèo được để riêng bằng túi giữ nhiệt.',
];

export const DetailSlideOver: React.FC<DetailSlideOverProps> = ({ item, onClose, onAskAgent }) => {
  if (!item) return null;

  const rating = item.rating ?? item.score ?? 4.5;
  const categoryTag = item.category || item.cuisine || 'Đối thủ trực tiếp';
  const quotes = item.review_quotes && item.review_quotes.length > 0 ? item.review_quotes : DEFAULT_QUOTES;
  const dimensions = item.dimensions && item.dimensions.length > 0 ? item.dimensions : DEFAULT_DIMENSIONS;

  return (
    <>
      {/* Backdrop overlay */}
      <div
        className="fixed inset-0 bg-black/40 z-40 transition-opacity duration-300"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer panel */}
      <div className="fixed inset-y-0 right-0 z-50 w-full max-w-[420px] bg-[#FFFFFF] dark:bg-[#1F2937] border-l border-[#E5E7EB] dark:border-[#374151] shadow-2xl flex flex-col transition-transform duration-300 ease-in-out">
        {/* Header */}
        <div className="p-4 border-b border-[#E5E7EB] dark:border-[#374151] flex items-start justify-between bg-[#FFFFFF] dark:bg-[#1F2937]">
          <div className="space-y-1 pr-2">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="font-bold text-base text-[#111827] dark:text-[#FFFFFF]">{item.name}</h3>
              <span className="px-2 py-0.5 text-xs bg-[#28BDBF]/10 text-[#00A398] dark:text-[#28BDBF] font-semibold border border-[#28BDBF]/20 rounded-none">
                {categoryTag}
              </span>
            </div>
            <p className="text-xs text-[#666666] dark:text-[#9CA3AF]">
              Mã quán: #{item.merchant_id} • Khoảng cách: {item.distance_km} km
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-[#666666] hover:text-[#353535] dark:text-[#9CA3AF] dark:hover:text-[#FFFFFF] transition-colors rounded-none"
            aria-label="Đóng bảng xem trước"
          >
            <SVGIcon name="close" className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-4 flex-1 overflow-y-auto space-y-5 text-sm text-[#353535] dark:text-[#FFFFFF]">
          {/* Cuisine & Basic Stats */}
          <div className="p-3 bg-[#F9F9FF] dark:bg-[#111827] border border-[#E5E7EB] dark:border-[#374151] rounded-none space-y-2">
            <div className="flex justify-between items-center text-xs">
              <span className="font-semibold text-[#666666] dark:text-[#9CA3AF]">LOẠI HÌNH ẨM THỰC</span>
              <span className="font-semibold text-[#E3BB42]">★ {rating.toFixed(1)} / 5.0</span>
            </div>
            <p className="font-medium text-sm text-[#111827] dark:text-[#FFFFFF]">{item.cuisine}</p>
            {item.address && (
              <p className="text-xs text-[#666666] dark:text-[#9CA3AF] pt-1 border-t border-[#E5E7EB] dark:border-[#374151]">
                📍 {item.address}
              </p>
            )}
          </div>

          {/* Review Evidence Quotes */}
          <div>
            <h5 className="font-semibold text-xs text-[#666666] dark:text-[#9CA3AF] mb-2 tracking-wide uppercase">
              BẰNG CHỨNG ĐÁNH GIÁ (REVIEWS)
            </h5>
            <div className="space-y-2">
              {quotes.map((quote, idx) => (
                <div
                  key={idx}
                  className="p-2.5 bg-[#FFFFFF] dark:bg-[#111827] border border-[#E5E7EB] dark:border-[#374151] rounded-none text-xs text-[#353535] dark:text-[#E5E7EB] italic"
                >
                  {quote}
                </div>
              ))}
            </div>
          </div>

          {/* 8-Dimension Comparative Highlights */}
          <div>
            <h5 className="font-semibold text-xs text-[#666666] dark:text-[#9CA3AF] mb-3 tracking-wide uppercase">
              PHÂN TÍCH 8 CHIỀU SO SÁNH
            </h5>
            <div className="space-y-3">
              {dimensions.map((dim, idx) => (
                <div key={idx} className="p-2.5 border border-[#E5E7EB] dark:border-[#374151] bg-[#FFFFFF] dark:bg-[#111827] rounded-none text-xs">
                  <div className="flex justify-between items-center mb-1">
                    <span className="font-bold text-[#111827] dark:text-[#FFFFFF]">{dim.dimension}</span>
                    <span className="font-semibold text-[#00A398] dark:text-[#28BDBF]">{dim.score.toFixed(1)}/10</span>
                  </div>
                  {/* Score bar */}
                  <div className="w-full h-1.5 bg-[#EEEEEE] dark:bg-[#374151] rounded-none mb-1.5 overflow-hidden">
                    <div
                      className="h-full bg-[#28BDBF] transition-all duration-300"
                      style={{ width: `${(dim.score / 10) * 100}%` }}
                    />
                  </div>
                  <p className="text-[#666666] dark:text-[#9CA3AF] text-[11px] leading-tight">
                    {dim.comparisonNote}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Footer Action */}
        <div className="p-4 border-t border-[#E5E7EB] dark:border-[#374151] bg-[#FFFFFF] dark:bg-[#1F2937]">
          <button
            onClick={() => {
              onAskAgent(`Hãy so sánh chi tiết điểm mạnh yếu giữa quán của tôi và ${item.name}`);
              onClose();
            }}
            className="w-full py-2.5 bg-[#28BDBF] hover:bg-[#00A398] text-[#FFFFFF] font-bold text-xs rounded-none transition-colors duration-200 uppercase tracking-wider"
          >
            Hỏi Agent về đối thủ này
          </button>
        </div>
      </div>
    </>
  );
};

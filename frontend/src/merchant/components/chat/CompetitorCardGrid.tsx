import React from 'react';
import { CompetitorItem } from '../../types/merchantChat';
import { SVGIcon } from '../common/SVGIcon';

interface CompetitorCardGridProps {
  competitors: CompetitorItem[];
  onSelect: (item: CompetitorItem) => void;
}

export const CompetitorCardGrid: React.FC<CompetitorCardGridProps> = ({ competitors, onSelect }) => {
  if (!competitors || competitors.length === 0) return null;

  return (
    <div className="my-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
      {competitors.map((comp) => {
        const rating = comp.rating ?? comp.score ?? 4.5;
        return (
          <div
            key={comp.merchant_id}
            onClick={() => onSelect(comp)}
            className="p-4 border border-[#E5E7EB] dark:border-[#374151] bg-[#FFFFFF] dark:bg-[#1F2937] hover:border-[#28BDBF] rounded-none cursor-pointer transition-colors duration-200 shadow-sm flex flex-col justify-between"
          >
            <div>
              <div className="flex items-start justify-between gap-2 mb-1.5">
                <h4 className="font-bold text-sm text-[#111827] dark:text-[#FFFFFF] line-clamp-1 flex items-center gap-1.5">
                  <SVGIcon name="store" className="w-4 h-4 text-[#28BDBF] shrink-0" />
                  <span>{comp.name}</span>
                </h4>
                <span className="px-2 py-0.5 text-xs bg-[#EEEEEE] dark:bg-[#374151] text-[#353535] dark:text-[#E5E7EB] font-medium rounded-none whitespace-nowrap shrink-0">
                  {comp.distance_km} km
                </span>
              </div>

              <div className="flex items-center justify-between text-xs text-[#666666] dark:text-[#9CA3AF] mb-3">
                <span className="truncate">{comp.cuisine}</span>
                <span className="flex items-center gap-1 font-semibold text-[#E3BB42] shrink-0">
                  ★ {rating.toFixed(1)}
                </span>
              </div>
            </div>

            <button
              onClick={(e) => {
                e.stopPropagation();
                onSelect(comp);
              }}
              className="text-xs font-bold text-[#28BDBF] hover:text-[#00A398] flex items-center gap-1 transition-colors self-start"
            >
              Xem chi tiết & So sánh →
            </button>
          </div>
        );
      })}
    </div>
  );
};

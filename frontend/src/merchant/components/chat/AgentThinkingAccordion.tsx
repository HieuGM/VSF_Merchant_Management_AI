import React, { useState } from 'react';
import { AgentStepLog } from '../../types/merchantChat';
import { SVGIcon } from '../common/SVGIcon';

export interface AgentThinkingAccordionProps {
  logs?: AgentStepLog[];
  isStreaming?: boolean;
  traceId?: string;
}

export const AgentThinkingAccordion: React.FC<AgentThinkingAccordionProps> = ({
  logs = [],
  isStreaming = false,
  traceId,
}) => {
  const [isOpen, setIsOpen] = useState(false);

  const getStepTypeColor = (type: AgentStepLog['type']) => {
    switch (type) {
      case 'agent_start':
        return 'text-[#28BDBF] dark:text-[#28BDBF]';
      case 'tool_call':
        return 'text-[#E3BB42] dark:text-[#E3BB42]';
      case 'tool_result':
        return 'text-[#00A398] dark:text-[#00A398]';
      default:
        return 'text-[#00A398] dark:text-[#00A398]';
    }
  };

  const getHeaderLabel = () => {
    if (isStreaming) {
      return 'Advisor Agent đang suy luận...';
    }
    const stepCountStr = logs.length > 0 ? `${logs.length} bước • ` : '';
    const traceStr = traceId ? `Trace ID: ${traceId}` : 'Hoàn thành suy luận';
    return `Đã hoàn thành suy luận (${stepCountStr}${traceStr})`;
  };

  return (
    <div className="my-2 border border-[#E5E7EB] dark:border-[#374151] bg-[#F9F9FF] dark:bg-[#1F2937] text-[#353535] dark:text-[#FFFFFF] text-xs transition-colors">
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="w-full px-3 py-2 flex items-center justify-between font-medium hover:bg-[#EEEEEE] dark:hover:bg-[#374151] transition-colors focus:outline-none"
        aria-expanded={isOpen}
      >
        <div className="flex items-center space-x-2">
          {isStreaming ? (
            <span className="w-2.5 h-2.5 rounded-full bg-[#28BDBF] animate-pulse flex-shrink-0" />
          ) : (
            <SVGIcon name="check" className="w-3.5 h-3.5 text-[#00A398] flex-shrink-0" />
          )}
          <span className="truncate">{getHeaderLabel()}</span>
        </div>
        <SVGIcon
          name="chevron-down"
          className={`w-3.5 h-3.5 text-[#666666] dark:text-[#9CA3AF] transition-transform duration-200 flex-shrink-0 ${
            isOpen ? 'rotate-180' : ''
          }`}
        />
      </button>

      {isOpen && (
        <div className="p-3 border-t border-[#E5E7EB] dark:border-[#374151] space-y-2">
          {logs.length === 0 ? (
            <div className="text-[#666666] dark:text-[#9CA3AF] italic">
              Đang phân tích dữ liệu 8 chiều & đối thủ...
            </div>
          ) : (
            logs.map((log) => (
              <div key={log.id} className="flex items-start space-x-2 font-mono text-[11px] leading-relaxed">
                <span className={`font-semibold uppercase flex-shrink-0 ${getStepTypeColor(log.type)}`}>
                  [{log.type}]
                </span>
                <div className="flex-1 break-words">
                  <span className="font-semibold text-[#111827] dark:text-[#FFFFFF]">{log.name}: </span>
                  <span className="text-[#353535] dark:text-[#E5E7EB]">{log.detail}</span>
                  {log.durationMs !== undefined && (
                    <span className="ml-1.5 text-[#666666] dark:text-[#9CA3AF] text-[10px]">
                      ({log.durationMs}ms)
                    </span>
                  )}
                </div>
                {log.timestamp && (
                  <span className="text-[#666666] dark:text-[#9CA3AF] text-[10px] flex-shrink-0">
                    {log.timestamp}
                  </span>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};

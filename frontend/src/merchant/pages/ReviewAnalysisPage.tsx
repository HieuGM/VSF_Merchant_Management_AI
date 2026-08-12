import { useEffect, useState, useMemo } from 'react';
import { fetchMerchantReviews, type MerchantReviewItem } from '../api/merchantProfileApi';

export function ReviewAnalysisPage({ merchantId }: { merchantId: string }) {
  const [reviews, setReviews] = useState<MerchantReviewItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [sentimentFilter, setSentimentFilter] = useState<'all' | 'positive' | 'neutral' | 'negative'>('all');
  const [ratingFilter, setRatingFilter] = useState<number | 'all'>('all');

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchMerchantReviews(merchantId)
      .then((res) => {
        if (active) {
          setReviews(res.reviews || []);
          setLoading(false);
        }
      })
      .catch(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [merchantId]);

  const stats = useMemo(() => {
    if (!reviews.length) return { avg: '0.0', total: 0, pos: 0, neu: 0, neg: 0 };
    const total = reviews.length;
    const sum = reviews.reduce((acc, r) => acc + (r.rating || 5), 0);
    const pos = reviews.filter((r) => r.sentiment === 'positive').length;
    const neu = reviews.filter((r) => r.sentiment === 'neutral').length;
    const neg = reviews.filter((r) => r.sentiment === 'negative').length;
    return {
      avg: (sum / total).toFixed(1),
      total,
      pos: Math.round((pos / total) * 100),
      neu: Math.round((neu / total) * 100),
      neg: Math.round((neg / total) * 100),
    };
  }, [reviews]);

  const filteredReviews = useMemo(() => {
    return reviews.filter((r) => {
      if (sentimentFilter !== 'all' && r.sentiment !== sentimentFilter) return false;
      if (ratingFilter !== 'all') {
        const star = Math.floor(r.rating || 5);
        if (star !== ratingFilter) return false;
      }
      if (search && !r.text.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [reviews, sentimentFilter, ratingFilter, search]);

  return (
    <div className="h-full overflow-y-auto chat-scrollbar bg-[#f8fafc] p-6 pb-20 space-y-6">
      {/* Header Banner - Xanh SM Brand Styling */}
      <div className="bg-gradient-to-r from-[#00a398] to-[#007a73] rounded-2xl p-6 text-white shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-teal-100 uppercase tracking-wider mb-1">
            <span>Dữ Liệu Đánh Giá Thực Tế</span>
            <span>•</span>
            <span>Merchant #{merchantId}</span>
          </div>
          <h1 className="text-2xl font-extrabold flex items-center gap-2 text-white">
            ⭐ Phân Tích Nhận Xét Khách Hàng
          </h1>
          <p className="text-teal-50 text-sm mt-1">
            Tổng hợp ý kiến phản hồi và đánh giá từ người dùng ứng dụng Xanh SM.
          </p>
        </div>
        <div className="bg-white/15 backdrop-blur-md px-6 py-3 rounded-xl border border-white/20 flex items-center gap-4 text-center">
          <div>
            <div className="text-3xl font-extrabold text-amber-300">{stats.avg} / 5.0</div>
            <div className="text-xs text-teal-100">{stats.total} đánh giá</div>
          </div>
        </div>
      </div>

      {/* Metrics Breakdown Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white border border-emerald-200 rounded-xl p-4 flex items-center justify-between shadow-sm">
          <div>
            <div className="text-xs font-bold text-emerald-700 uppercase">TÍCH CỰC (POSITIVE)</div>
            <div className="text-2xl font-extrabold text-slate-800 mt-1">{stats.pos}%</div>
          </div>
          <span className="text-3xl">😊</span>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4 flex items-center justify-between shadow-sm">
          <div>
            <div className="text-xs font-bold text-slate-500 uppercase">TRUNG TÍNH (NEUTRAL)</div>
            <div className="text-2xl font-extrabold text-slate-800 mt-1">{stats.neu}%</div>
          </div>
          <span className="text-3xl">😐</span>
        </div>
        <div className="bg-white border border-rose-200 rounded-xl p-4 flex items-center justify-between shadow-sm">
          <div>
            <div className="text-xs font-bold text-rose-600 uppercase">CẦN CẢI THIỆN (NEGATIVE)</div>
            <div className="text-2xl font-extrabold text-slate-800 mt-1">{stats.neg}%</div>
          </div>
          <span className="text-3xl">😞</span>
        </div>
      </div>

      {/* Controls & Filters Bar */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-col md:flex-row gap-4 items-center justify-between">
        <div className="relative w-full md:w-80">
          <input
            type="text"
            placeholder="Tìm kiếm nội dung đánh giá..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-slate-50 border border-slate-300 rounded-lg px-4 py-2 text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:border-[#00a398]"
          />
        </div>

        {/* Sentiment Filters */}
        <div className="flex flex-wrap items-center gap-2 w-full md:w-auto">
          <span className="text-xs text-slate-500 font-semibold mr-1">Cảm xúc:</span>
          {(['all', 'positive', 'neutral', 'negative'] as const).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setSentimentFilter(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                sentimentFilter === s
                  ? 'bg-[#00a398] text-white shadow-sm'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {s === 'all' ? 'Tất cả' : s === 'positive' ? 'Tích cực' : s === 'neutral' ? 'Trung tính' : 'Tiêu cực'}
            </button>
          ))}
        </div>

        {/* Rating Star Filters */}
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-slate-500 font-semibold mr-1">Sao:</span>
          {(['all', 5, 4, 3, 2, 1] as const).map((star) => (
            <button
              key={String(star)}
              type="button"
              onClick={() => setRatingFilter(star)}
              className={`px-2.5 py-1 rounded-md text-xs font-bold ${
                ratingFilter === star
                  ? 'bg-amber-400 text-slate-900 shadow-sm'
                  : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
              }`}
            >
              {star === 'all' ? 'Tất cả' : `${star}★`}
            </button>
          ))}
        </div>
      </div>

      {/* Reviews Scrollable Grid */}
      {loading ? (
        <div className="text-center py-12 text-slate-500 animate-pulse">Đang tải nhận xét khách hàng...</div>
      ) : filteredReviews.length === 0 ? (
        <div className="text-center py-12 bg-white border border-slate-200 rounded-xl text-slate-500">
          Không tìm thấy nhận xét nào phù hợp.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filteredReviews.map((rev) => (
            <div
              key={rev.review_id}
              className="bg-white border border-slate-200 hover:border-[#00a398]/60 rounded-xl p-5 shadow-sm transition-all flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-1 text-amber-500 font-bold text-sm">
                    {'★'.repeat(Math.round(rev.rating || 5))}
                    <span className="text-xs text-slate-500 ml-1">({rev.rating || 5}/5.0)</span>
                  </div>
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                      rev.sentiment === 'positive'
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        : rev.sentiment === 'negative'
                        ? 'bg-rose-50 text-rose-700 border border-rose-200'
                        : 'bg-slate-100 text-slate-700'
                    }`}
                  >
                    {rev.sentiment}
                  </span>
                </div>
                <p className="text-slate-700 text-sm leading-relaxed mb-4">{rev.text}</p>
              </div>

              <div className="flex items-center justify-between text-xs text-slate-400 border-t border-slate-100 pt-3">
                <span>Nguồn: {rev.source_kind}</span>
                <span>{rev.created_at ? new Date(rev.created_at).toLocaleDateString('vi-VN') : 'Mới đây'}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

import { useEffect, useState } from 'react';
import {
  fetchMerchantProfile,
  fetchMerchantMenu,
  type MenuItemData,
} from '../api/merchantProfileApi';
import type { MerchantProfileData } from '../types/merchantChat';

export function MerchantInfoMenuPage({ merchantId }: { merchantId: string }) {
  const [activeTab, setActiveTab] = useState<'profile' | 'menu'>('menu');
  const [profile, setProfile] = useState<MerchantProfileData | null>(null);
  const [menuItems, setMenuItems] = useState<MenuItemData[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([
      fetchMerchantProfile(merchantId).catch(() => null),
      fetchMerchantMenu(merchantId).catch(() => ({ count: 0, menu_items: [] })),
    ]).then(([profRes, menuRes]) => {
      if (active) {
        if (profRes) setProfile(profRes);
        setMenuItems(menuRes.menu_items || []);
        setLoading(false);
      }
    });
    return () => {
      active = false;
    };
  }, [merchantId]);

  const categories = Array.from(new Set(menuItems.map((m) => m.category || 'Món chính')));

  const filteredMenu = menuItems.filter((item) => {
    if (selectedCategory !== 'all' && (item.category || 'Món chính') !== selectedCategory) return false;
    if (search && !item.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="h-full overflow-y-auto chat-scrollbar bg-[#f8fafc] p-6 pb-20 space-y-6">
      {/* Top Banner - Xanh SM Theme */}
      <div className="bg-gradient-to-r from-[#00a398] to-[#007a73] rounded-2xl p-6 text-white shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-teal-100 uppercase tracking-wider mb-1">
            <span>ĐỐI TÁC XANH SM MERCHANT</span>
            <span>•</span>
            <span>MÃ: {merchantId}</span>
          </div>
          <h1 className="text-2xl font-extrabold text-white">
            {profile?.metadata?.name || `Nhà Hàng #${merchantId}`}
          </h1>
          <p className="text-teal-50 text-sm mt-1">
            {profile?.metadata?.cuisine || 'Ẩm thực phong phú'} • {profile?.metadata?.city || 'TP. Hồ Chí Minh'}
          </p>
        </div>

        {/* Navigation Tabs */}
        <div className="flex items-center gap-2 bg-white/15 backdrop-blur-md p-1.5 rounded-xl border border-white/20">
          <button
            type="button"
            onClick={() => setActiveTab('menu')}
            className={`px-5 py-2.5 rounded-lg text-xs font-bold transition-all ${
              activeTab === 'menu'
                ? 'bg-white text-[#007a73] shadow-sm'
                : 'text-white hover:bg-white/10'
            }`}
          >
            🍜 THỰC ĐƠN / MENU ({menuItems.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('profile')}
            className={`px-5 py-2.5 rounded-lg text-xs font-bold transition-all ${
              activeTab === 'profile'
                ? 'bg-white text-[#007a73] shadow-sm'
                : 'text-white hover:bg-white/10'
            }`}
          >
            🏢 THÔNG TIN CỬA HÀNG
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12 text-slate-500 animate-pulse">Đang tải thông tin thực đơn...</div>
      ) : activeTab === 'profile' ? (
        /* TAB 1: PROFILE & OPERATIONAL METRICS */
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* General Info Card */}
            <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-4 shadow-sm">
              <h2 className="text-base font-bold text-[#00a398] flex items-center gap-2 border-b border-slate-100 pb-3">
                <span>📍 Thông Tin Vận Hành</span>
              </h2>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-slate-400 text-xs font-semibold block">TÊN CỬA HÀNG</span>
                  <span className="text-slate-800 font-bold">{profile?.metadata?.name || 'Green SM Merchant'}</span>
                </div>
                <div>
                  <span className="text-slate-400 text-xs font-semibold block">MÃ MERCHANT</span>
                  <span className="text-slate-800 font-bold">{merchantId}</span>
                </div>
                <div>
                  <span className="text-slate-400 text-xs font-semibold block">TỈNH / THÀNH PHỐ</span>
                  <span className="text-slate-800 font-semibold">{profile?.metadata?.city || 'N/A'}</span>
                </div>
                <div>
                  <span className="text-slate-400 text-xs font-semibold block">LOẠI HÌNH ẨM THỰC</span>
                  <span className="text-slate-800 font-semibold">{profile?.metadata?.cuisine || 'N/A'}</span>
                </div>
                <div>
                  <span className="text-slate-400 text-xs font-semibold block">TRẠNG THÁI</span>
                  <span className="inline-block px-2.5 py-0.5 rounded bg-emerald-50 text-emerald-700 text-xs font-bold border border-emerald-200 mt-0.5">
                    ĐANG HOẠT ĐỘNG
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 text-xs font-semibold block">PHÂN CẤP TIER</span>
                  <span className="text-amber-600 font-bold uppercase">{profile?.tier || 'HERO'}</span>
                </div>
              </div>
            </div>

            {/* Quality Scores */}
            <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-4 shadow-sm">
              <h2 className="text-base font-bold text-amber-600 flex items-center gap-2 border-b border-slate-100 pb-3">
                <span>⭐ Điểm Đánh Giá Chất Lượng</span>
              </h2>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div className="bg-slate-50 p-3 rounded-lg border border-slate-200">
                  <span className="text-slate-500 text-xs font-semibold block">Chất Lượng Món Ăn</span>
                  <span className="text-[#00a398] font-extrabold text-lg">
                    {profile?.scores?.food_quality ? `${(profile.scores.food_quality * 10).toFixed(1)}/10` : '9.2/10'}
                  </span>
                </div>
                <div className="bg-slate-50 p-3 rounded-lg border border-slate-200">
                  <span className="text-slate-500 text-xs font-semibold block">Tốc Độ Phục Vụ</span>
                  <span className="text-[#00a398] font-extrabold text-lg">
                    {profile?.scores?.waiting_time ? `${(profile.scores.waiting_time * 10).toFixed(1)}/10` : '8.8/10'}
                  </span>
                </div>
                <div className="bg-slate-50 p-3 rounded-lg border border-slate-200">
                  <span className="text-slate-500 text-xs font-semibold block">Chất Lượng Đóng Gói</span>
                  <span className="text-[#00a398] font-extrabold text-lg">
                    {profile?.scores?.packaging ? `${(profile.scores.packaging * 10).toFixed(1)}/10` : '9.0/10'}
                  </span>
                </div>
                <div className="bg-slate-50 p-3 rounded-lg border border-slate-200">
                  <span className="text-slate-500 text-xs font-semibold block">Hình Ảnh Thực Đơn</span>
                  <span className="text-[#00a398] font-extrabold text-lg">
                    {profile?.scores?.image_quality ? `${(profile.scores.image_quality * 10).toFixed(1)}/10` : '8.5/10'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : (
        /* TAB 2: FULL MENU & DISHES LIST (WITH IMAGES) */
        <div className="space-y-6">
          {/* Controls Bar */}
          <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-col md:flex-row gap-4 items-center justify-between">
            <input
              type="text"
              placeholder="Tìm tên món ăn trong menu..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full md:w-80 bg-slate-50 border border-slate-300 rounded-lg px-4 py-2 text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:border-[#00a398]"
            />

            {/* Category Filter Pills */}
            <div className="flex items-center gap-2 flex-wrap">
              <button
                type="button"
                onClick={() => setSelectedCategory('all')}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                  selectedCategory === 'all'
                    ? 'bg-[#00a398] text-white shadow-sm'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                Tất cả nhóm ({menuItems.length})
              </button>
              {categories.map((cat) => (
                <button
                  key={cat}
                  type="button"
                  onClick={() => setSelectedCategory(cat)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                    selectedCategory === cat
                      ? 'bg-[#00a398] text-white shadow-sm'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>

          {/* Dishes Grid */}
          {filteredMenu.length === 0 ? (
            <div className="text-center py-12 bg-white border border-slate-200 rounded-xl text-slate-500">
              Chưa có món ăn nào trong danh mục này.
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
              {filteredMenu.map((item) => (
                <div
                  key={item.item_id}
                  className="bg-white border border-slate-200 hover:border-[#00a398]/60 rounded-xl overflow-hidden shadow-sm hover:shadow-md transition-all flex flex-col justify-between"
                >
                  <div>
                    {/* Dish Image Display */}
                    <div className="relative w-full h-44 bg-slate-100 overflow-hidden">
                      {item.image_url ? (
                        <img
                          src={item.image_url}
                          alt={item.name}
                          className="w-full h-full object-cover transition-transform duration-300 hover:scale-105"
                          onError={(e) => {
                            // Fallback if image URL fails to load
                            (e.target as HTMLImageElement).src =
                              'https://images.unsplash.com/photo-1546069901-ba9599a7e63c?auto=format&fit=crop&w=500&q=80';
                          }}
                        />
                      ) : (
                        <div className="w-full h-full bg-gradient-to-br from-teal-50 to-slate-100 flex flex-col items-center justify-center text-slate-400">
                          <span className="text-4xl mb-1">🍲</span>
                          <span className="text-[11px] font-semibold text-slate-500">Xanh SM Menu</span>
                        </div>
                      )}

                      {/* Dish Badges */}
                      <div className="absolute top-2 left-2 flex items-center gap-1">
                        <span className="text-[10px] font-extrabold uppercase px-2.5 py-1 rounded-md bg-slate-900/80 backdrop-blur-md text-white border border-white/20 shadow-sm">
                          {item.category || 'Món chính'}
                        </span>
                      </div>
                      <div className="absolute top-2 right-2">
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                            item.is_available
                              ? 'bg-emerald-500 text-white shadow-sm'
                              : 'bg-rose-500 text-white'
                          }`}
                        >
                          {item.is_available ? 'Còn hàng' : 'Hết hàng'}
                        </span>
                      </div>
                    </div>

                    <div className="p-4">
                      <h3 className="text-sm font-bold text-slate-900 line-clamp-1">{item.name}</h3>
                      {item.description ? (
                        <p className="text-slate-500 text-xs mt-1 line-clamp-2 leading-relaxed">{item.description}</p>
                      ) : (
                        <p className="text-slate-400 text-xs italic mt-1">Chưa có mô tả món ăn</p>
                      )}
                    </div>
                  </div>

                  <div className="p-4 pt-0 flex items-center justify-between border-t border-slate-100 mt-2">
                    <div>
                      <span className="text-[#00a398] font-extrabold text-base">
                        {item.price.toLocaleString('vi-VN')} đ
                      </span>
                      {item.discount_price && (
                        <span className="text-xs text-slate-400 line-through ml-2">
                          {item.discount_price.toLocaleString('vi-VN')} đ
                        </span>
                      )}
                    </div>
                    {item.total_like > 0 && (
                      <span className="text-xs text-amber-500 flex items-center gap-1 font-bold">
                        ❤️ {item.total_like}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

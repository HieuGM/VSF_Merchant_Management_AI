export function ChatHeader({
  merchantName,
  onOpenMenu,
  onOpenMobileMap,
}: {
  merchantName: string;
  onOpenMenu: () => void;
  onOpenMobileMap?: () => void;
}) {
  return (
    <header className="chat-header">
      <button type="button" className="mobile-menu" onClick={onOpenMenu} aria-label="Mở điều hướng">☰</button>

      {/* Top Bar Search Input */}
      <div className="header-search">
        <input type="text" placeholder="Tìm kiếm đối thủ, khu vực..." aria-label="Tìm kiếm đối thủ, khu vực" readOnly />
      </div>

      {/* Right User Controls */}
      <div className="header-actions">
        {onOpenMobileMap && (
          <button
            type="button"
            className="mobile-map-toggle-header-btn"
            onClick={onOpenMobileMap}
            aria-label="Mở bản đồ"
          >
            Map
          </button>
        )}
        <div className="user-profile-avatar" title={merchantName}>
          <svg width="36" height="36" viewBox="0 0 36 36" fill="none">
            <circle cx="18" cy="18" r="18" fill="#E0F2FE" />
            <path d="M18 19C20.2091 19 22 17.2091 22 15C22 12.7909 20.2091 11 18 11C15.7909 11 14 12.7909 14 15C14 17.2091 15.7909 19 18 19Z" fill="#0284C7" />
            <path d="M18 21C13.5817 21 10 23.5817 10 27H26C26 23.5817 22.4183 21 18 21Z" fill="#0284C7" />
          </svg>
        </div>
      </div>
    </header>
  );
}

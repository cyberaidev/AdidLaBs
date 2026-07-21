import {
  CloudIcon,
  UserIcon,
  HeartIcon,
  BagIcon,
  SearchIcon,
  ChatIcon,
} from "./icons.jsx";

// Top-right icon cluster in exact order (§5.3): search stub, cloud (architecture),
// chat (stylist drawer), user (green dot when authed), heart (wishlist),
// bag (live count).
export function CornerIcons({
  authed,
  wishlistCount,
  bagCount,
  onArchitecture,
  onChat,
  onAccount,
  onWishlist,
  onBag,
}) {
  return (
    <div className="corner-icons">
      <span className="search-stub" aria-hidden="true">
        <SearchIcon />
        SEARCH
      </span>

      <button
        type="button"
        className="icon-btn"
        aria-label="AWS architecture"
        onClick={onArchitecture}
      >
        <CloudIcon />
      </button>

      <button
        type="button"
        className="icon-btn"
        aria-label="Stylist chat"
        title="Stylist chat"
        onClick={onChat}
      >
        <ChatIcon />
      </button>

      <button type="button" className="icon-btn" aria-label="Account" onClick={onAccount}>
        <UserIcon />
        {authed && <span className="user-dot" aria-hidden="true" />}
      </button>

      <button
        type="button"
        className="icon-btn"
        aria-label="Wishlist"
        onClick={onWishlist}
      >
        <HeartIcon />
        {wishlistCount > 0 && <span className="icon-badge">{wishlistCount}</span>}
      </button>

      <button type="button" className="icon-btn" aria-label="Bag" onClick={onBag}>
        <BagIcon />
        {bagCount > 0 && <span className="icon-badge">{bagCount}</span>}
      </button>
    </div>
  );
}

import { useEffect } from "react";

// Shared right-side drawer shell (§5.13–5.15). role=dialog, aria-modal, ESC to close.
export function Drawer({ titleId, className, onClose, children }) {
  useEffect(() => {
    function onKeyDown(e) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <>
      <div className="drawer-scrim" onMouseDown={onClose} />
      <aside
        className={`drawer ${className ?? ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        {children}
      </aside>
    </>
  );
}

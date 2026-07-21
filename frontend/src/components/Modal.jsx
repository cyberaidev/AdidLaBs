import { useEffect, useRef } from "react";

// Accessible modal shell (§8): role=dialog, aria-modal, focus trap, labelled by title.
// dismissible=false (the registration gate) disables ESC and scrim-click.
export function Modal({ titleId, dismissible, onClose, children }) {
  const ref = useRef(null);

  useEffect(() => {
    // Move focus into the dialog itself (not its first input): keyboard and
    // screen-reader users land inside the modal, but no text caret blinks in
    // the middle of the page until a field is actually chosen.
    const node = ref.current;
    if (node) node.focus();

    function onKeyDown(e) {
      if (e.key === "Escape" && dismissible && onClose) {
        onClose();
        return;
      }
      if (e.key !== "Tab" || !node) return;
      const items = node.querySelectorAll(
        'input, button, [href], select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [dismissible, onClose]);

  return (
    <div
      className="scrim"
      onMouseDown={(e) => {
        if (dismissible && onClose && e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        style={{ outline: "none" }}
        ref={ref}
      >
        {children}
      </div>
    </div>
  );
}

import { Wordmark } from "./Wordmark.jsx";
import { NavBar } from "./NavBar.jsx";
import { CornerIcons } from "./CornerIcons.jsx";

// Sticky header: wordmark left, centered nav, corner icons right (§5.2).
export function Header(props) {
  return (
    <header className="header">
      <div className="container">
        <Wordmark className="header-word" />
        <NavBar />
        <CornerIcons {...props} />
      </div>
    </header>
  );
}

import { useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import LocationsPage from "./pages/LocationsPage";
import LowStockPage from "./pages/LowStockPage";
import MovementsPage from "./pages/MovementsPage";
import NewMovementPage from "./pages/NewMovementPage";
import OverviewPage from "./pages/OverviewPage";
import ProductLedgerPage from "./pages/ProductLedgerPage";
import ProductsPage from "./pages/ProductsPage";
import ReconcilePage from "./pages/ReconcilePage";
import ValuationPage from "./pages/ValuationPage";

const NAV = [
  { to: "/", label: "Stock overview", end: true },
  { to: "/movements/new", label: "New movement" },
  { to: "/movements", label: "History", end: true },
  { to: "/products", label: "Products" },
  { to: "/locations", label: "Locations" },
  { to: "/reports/low-stock", label: "Low stock" },
  { to: "/reports/valuation", label: "Valuation" },
  { to: "/reconcile", label: "Reconcile" },
];

export default function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">Stock Ledger</span>
        <button
          type="button"
          className="menu-toggle"
          aria-expanded={menuOpen}
          aria-controls="main-nav"
          onClick={() => setMenuOpen((open) => !open)}
        >
          Menu
        </button>
        <nav id="main-nav" className={menuOpen ? "open" : ""} aria-label="Main">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} onClick={() => setMenuOpen(false)}>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="content">
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/movements/new" element={<NewMovementPage />} />
          <Route path="/movements" element={<MovementsPage />} />
          <Route path="/products" element={<ProductsPage />} />
          <Route path="/products/:productId" element={<ProductLedgerPage />} />
          <Route path="/locations" element={<LocationsPage />} />
          <Route path="/reports/low-stock" element={<LowStockPage />} />
          <Route path="/reports/valuation" element={<ValuationPage />} />
          <Route path="/reconcile" element={<ReconcilePage />} />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
    </div>
  );
}

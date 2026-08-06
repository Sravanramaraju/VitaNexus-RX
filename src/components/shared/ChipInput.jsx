import { X } from "lucide-react";
import { useState } from "react";
import { searchBrand } from "../../lib/otcMapping";

export default function ChipInput({
  items = [],
  onChange,
  placeholder = "Search a brand",
}) {
  const [query, setQuery] = useState("");
  const matches = searchBrand(query);
  const add = (item) => {
    if (!items.some((current) => current.brand === item.brand))
      onChange([...items, item]);
    setQuery("");
  };
  return (
    <div className="space-y-2">
      <div className="relative">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="input"
          placeholder={placeholder}
        />
        {query && (
          <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-lg border border-border bg-card shadow-md dark:border-slate-600 dark:bg-slate-800">
            {matches.length ? (
              matches.map((item) => (
                <button
                  type="button"
                  key={item.brand}
                  onClick={() => add(item)}
                  className="block w-full px-3 py-2 text-left text-sm hover:bg-primary/10"
                >
                  <strong>{item.brand}</strong>
                  <span className="block text-xs text-slate-500 dark:text-slate-400">
                    {item.generic}
                  </span>
                </button>
              ))
            ) : (
              <p className="px-3 py-2 text-xs text-slate-500">
                No matching brands
              </p>
            )}
          </div>
        )}
      </div>
      {items.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {items.map((item) => (
            <span
              key={item.brand}
              className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary"
            >
              {item.brand} ({item.generic}){" "}
              <button
                type="button"
                onClick={() =>
                  onChange(
                    items.filter((current) => current.brand !== item.brand),
                  )
                }
                aria-label={`Remove ${item.brand}`}
              >
                <X size={13} />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

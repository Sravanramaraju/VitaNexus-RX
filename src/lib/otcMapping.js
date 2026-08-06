import otcBrands from "../data/otcBrands.json";

export function searchBrand(query) {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return [];
  return otcBrands
    .filter(
      ({ brand, generic }) =>
        brand.toLowerCase().includes(normalized) ||
        generic.toLowerCase().includes(normalized),
    )
    .slice(0, 8);
}

export function searchCondition(query, list) {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return [];
  return list
    .filter((item) => item.toLowerCase().includes(normalized))
    .slice(0, 5);
}

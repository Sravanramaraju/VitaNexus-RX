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
    .slice(0, 8)
    .map((item) => ({ ...item, mappingSource: item.mappingSource || "Indian Medicine Dataset", mappingVersion: item.mappingVersion || "Imported terminology artifact" }));
}

export function resolveDrugInput(value) {
  if (!value) return null;
  return { enteredName: value.brand || value.generic, normalizedName: (value.brand || value.generic || "").trim().toLowerCase(), brand: value.brand || null, generic: value.generic, mappingSource: value.mappingSource || "Indian Medicine Dataset", mappingVersion: value.mappingVersion || "Imported terminology artifact" };
}

export function searchCondition(query, list) {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return [];
  return list
    .filter((item) => item.toLowerCase().includes(normalized))
    .slice(0, 5);
}

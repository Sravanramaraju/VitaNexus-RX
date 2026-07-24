import otcBrands from '../data/otcBrands.json'

export function searchBrand(query) {
  const normalized = query.trim().toLowerCase()
  if (!normalized) return []
  return otcBrands.filter(({ brand }) => brand.toLowerCase().includes(normalized)).slice(0, 5)
}

export function searchCondition(query, list) {
  const normalized = query.trim().toLowerCase()
  if (!normalized) return []
  return list.filter((item) => item.toLowerCase().includes(normalized)).slice(0, 5)
}

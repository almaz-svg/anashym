/** Original embedded photos from карточки.pdf, in PDF page order.
 * The PDF contains no names, so an administrator must assign each photo.
 */
export const PDF_PRODUCT_PHOTOS = Array.from({ length: 10 }, (_, index) => ({
  src: `/product-photos/photo-${String(index + 1).padStart(2, '0')}.jpg`,
  label: `Фото ${index + 1}`,
}))

export function productPhoto(product: { image_url?: string; name: string }): string {
  // None of the unnamed PDF photos can be verified as the seeded products.
  return product.image_url || ''
}

/* The workbench's act pages sit behind Cloudflare Access on index.fab.city. Access only
   guards requests that come through the zone, so the same pages on fci-index.pages.dev
   and every preview deployment would stay open. Send those to the custom domain, where
   Access asks for sign-in. _routes.json (written by build.sh) limits this Function to
   the protected paths, so nothing else on the site runs through it. */
const PROTECTED = /^\/operate\/(intake|review-queue|sovereignty)(\.html)?\/?$/;

export async function onRequest({ request, next }) {
  const url = new URL(request.url);
  if (url.hostname !== "index.fab.city" && PROTECTED.test(url.pathname)) {
    return Response.redirect("https://index.fab.city" + url.pathname + url.search, 302);
  }
  return next();
}

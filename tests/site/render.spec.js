// What each view draws when its URL is loaded cold.
//
// Every view is a URL a visitor can be linked straight into, so "does it draw
// at all" is a real question for each of them separately — a view that throws
// during render leaves the section empty and the page otherwise intact, which
// is exactly the failure nobody notices from the front page.

import { test, expect } from "@playwright/test";

// The attribute the package tests drive. Long-lived and small enough that its
// version table and both charts render quickly.
const ATTR = "ripgrep";

// How many revision rows the first window holds — REV_PAGE in site/js/config.js.
const REV_PAGE = 150;

// The four totals across the top of the stats view. Named rather than counted:
// the view carries a second KPI row for the cache census, so a bare count of
// .kpi says nothing about whether these four are the ones that drew.
const TOTALS = [
  "versioned attributes today",
  "package versions ever",
  "attributes added all time",
  "attributes removed all time",
];

// Below this the stats view has quietly lost a chart.
const MIN_STAT_CHARTS = 8;

test("the packages view draws a version table and both charts", async ({
  page,
}) => {
  // The URL a search engine renders 30,000 times. Asserts the join against
  // revisions.json landed (every row names a revision) and that both
  // package charts drew, since each reads a different shard.
  await page.goto(`/?pkg=${ATTR}`);

  const rows = page.locator(".row.cols-ver");
  await expect(rows.first()).toBeVisible();
  const versions = await (
    await page.request.get("/versions/pkgs/ri.json")
  ).json();
  await expect(rows).toHaveCount(Object.keys(versions.attrs[ATTR]).length);

  await expect(
    page.getByRole("heading", { name: /When each version was the one/ }),
  ).toBeVisible();
  const metadata = await (await page.request.get("/meta/pkgs/ri.json")).json();
  const measured = Object.values(metadata.attrs[ATTR]).filter(
    (entry) => entry.ns != null,
  );
  const weight = page.getByRole("heading", {
    name: /How heavy each version was/,
  });
  if (measured.length >= 3) await expect(weight).toBeVisible();
  else await expect(weight).toHaveCount(0);
});

test("the revisions view draws its first window of rows", async ({ page }) => {
  // The window is what keeps the page from laying out 1,500 rows, so its size
  // is behaviour worth pinning, not an implementation detail.
  await page.goto("/?view=revisions");

  const rows = page.locator(".row.cols-rev");
  await expect(rows.first()).toBeVisible();
  const revisions = await (await page.request.get("/revisions.json")).json();
  await expect(rows).toHaveCount(Math.min(REV_PAGE, revisions.length));
});

test("the releases view draws a row per release channel", async ({ page }) => {
  // Releases fetches its own releases.json now, so this also covers that the
  // view can load data by itself rather than being handed it by App.
  await page.goto("/?view=releases");

  const rows = page.locator(".row.cols-rel");
  await expect(rows.first()).toBeVisible();

  // Every release since 13.10, so the exact count moves every six months.
  expect(await rows.count()).toBeGreaterThan(20);
});

test("the stats view draws its totals and every chart", async ({ page }) => {
  // The charts are hand-rolled SVG over stats.json; one bad field takes out a
  // single chart and leaves the rest of the page looking healthy.
  await page.goto("/?view=stats");

  for (const total of TOTALS) {
    await expect(page.locator(".kpi .l", { hasText: total })).toBeVisible();
  }
  await expect
    .poll(() => page.locator("h3").count())
    .toBeGreaterThanOrEqual(MIN_STAT_CHARTS);
});

test("the summary line states the index totals", async ({ page }) => {
  // It reads stats.json, which no longer arrives with revisions.json — so
  // this is the check that the line still fills in on its own.
  await page.goto("/");
  await expect(page.locator("#stats")).toHaveText(
    /[\d,]+ package versions across [\d,]+ attributes, from [\d,]+ revisions/,
  );
});

test("a search finds a package by name", async ({ page }) => {
  // Typing rather than a ?q= URL: the input drives navigate() on every
  // keystroke, and the results come from names.json, which only this path
  // fetches.
  await page.goto("/");
  await page.getByRole("searchbox").fill(ATTR);

  const hit = page.locator("#results a.pkg").first();
  await expect(hit).toBeVisible();
  await expect(hit).toContainText(ATTR);
});

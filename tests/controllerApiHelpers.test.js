/**
 * @jest-environment jsdom
 */

import "whatwg-fetch";
import { setupServer } from "msw/node";
import { rest } from "msw";
import {
  fetchBaseline,
  fetchCascadeStatus,
  requestCascade,
  getCascadePreference,
  setCascadePreference,
} from "../frontend/src/panels/controller/apiHelpers.js";

const server = setupServer();

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const API_BASE = "http://localhost/api/local/controller";

describe("controller cascade API helpers", () => {
  test("fetchCascadeStatus resolves with payload", async () => {
    server.use(
      rest.get(`${API_BASE}/cascade/status`, (_req, res, ctx) =>
        res(ctx.json({ status: "completed", job: { job_id: "123", status: "completed" } })),
      ),
    );

    const result = await fetchCascadeStatus();
    expect(result).toEqual({
      status: "completed",
      job: { job_id: "123", status: "completed" },
    });
  });

  test("fetchCascadeStatus throws on backend error", async () => {
    server.use(
      rest.get(`${API_BASE}/cascade/status`, (_req, res, ctx) =>
        res(ctx.status(500), ctx.json({ detail: "cascade failed" })),
      ),
    );

    await expect(fetchCascadeStatus()).rejects.toThrow(/cascade failed/);
  });

  test("fetchBaseline returns baseline data", async () => {
    const payload = {
      encoder: { controls_count: 32 },
      led: { status: "completed" },
      updated_at: "2025-10-29T17:00:00Z",
    };
    server.use(
      rest.get(`${API_BASE}/baseline`, (_req, res, ctx) =>
        res(ctx.json(payload)),
      ),
    );

    const result = await fetchBaseline();
    expect(result.encoder.controls_count).toBe(32);
    expect(result.led.status).toBe("completed");
  });

  test("fetchBaseline throws when API returns non-200", async () => {
    server.use(
      rest.get(`${API_BASE}/baseline`, (_req, res, ctx) =>
        res(ctx.status(404), ctx.json({ detail: "not found" })),
      ),
    );

    await expect(fetchBaseline()).rejects.toThrow(/not found/);
  });

  test("requestCascade posts metadata and returns response", async () => {
    let receivedBody = null;
    server.use(
      rest.post(`${API_BASE}/cascade/apply`, async (req, res, ctx) => {
        receivedBody = await req.json();
        return res(
          ctx.json({
            status: "queued",
            job: { job_id: "abc", status: "queued" },
          }),
        );
      }),
    );

    const response = await requestCascade({
      metadata: { source: "test", changed_controls: ["p1.button1"] },
    });
    expect(response.status).toBe("queued");
    expect(receivedBody).toMatchObject({
      metadata: { source: "test", changed_controls: ["p1.button1"] },
      skip_led: false,
      skip_emulators: [],
    });
  });

  test("requestCascade throws on failure", async () => {
    server.use(
      rest.post(`${API_BASE}/cascade/apply`, (_req, res, ctx) =>
        res(ctx.status(500), ctx.json({ detail: "queue unavailable" })),
      ),
    );

    await expect(requestCascade()).rejects.toThrow(/queue unavailable/);
  });

  test("get/set cascade preference round trip", () => {
    window.localStorage.clear();
    expect(getCascadePreference("ask")).toBe("ask");
    setCascadePreference("auto");
    expect(getCascadePreference()).toBe("auto");
  });
});

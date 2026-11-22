export interface HealthResponse {
  status: "ok";
  database: { status: "not_configured" };
  scryfall: { status: "not_configured" };
  rules: { status: "not_configured" };
  ai: { status: "not_configured" };
}

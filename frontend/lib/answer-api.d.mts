import type { AnswerRequest, AnswerResponse } from "./api";

export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number);
}

export function resolveApiBaseUrl(
  configured: string | null | undefined,
  isDevelopment: boolean,
): string;

export function submitAnswerRequest(
  request: AnswerRequest,
  baseUrl: string,
): Promise<AnswerResponse>;

export function isAnswerResponse(value: unknown): value is AnswerResponse;

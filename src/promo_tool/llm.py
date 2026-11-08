from __future__ import annotations
import collections
import json
import os
import re
import time
import threading


def parse_json(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    start = min([i for i in (text.find("{"), text.find("[")) if i != -1], default=-1)
    if start == -1:
        raise ValueError("no JSON found in model output")
    return json.loads(text[start:])


class RateLimiter:
    """Thread-safe sliding-window rate limiter.

    Tracks the timestamps of the last `max_calls` requests.
    Before allowing a new call, it sleeps just long enough so that
    the oldest tracked request falls outside the `window_seconds` window.

    Default: 15 calls / 60 seconds  (Gemini free tier limit).
    """

    def __init__(self, max_calls: int = 15, window_seconds: float = 60.0):
        self.max_calls = max_calls
        self.window = window_seconds
        self._timestamps: collections.deque[float] = collections.deque()
        self._lock = threading.Lock()

    def wait(self):
        """Block until a request is allowed, then record the call."""
        with self._lock:
            now = time.monotonic()

            # Drop timestamps older than the window
            while self._timestamps and now - self._timestamps[0] >= self.window:
                self._timestamps.popleft()

            if len(self._timestamps) >= self.max_calls:
                # Must wait until the oldest call is `window` seconds old
                sleep_for = self.window - (now - self._timestamps[0])
                if sleep_for > 0:
                    time.sleep(sleep_for)

            self._timestamps.append(time.monotonic())


class LLM:
    """Thin wrapper around the Google Gemini API (google-genai SDK).

    Always returns parsed JSON. Respects the free-tier rate limit of
    15 requests per minute automatically — no manual sleep needed.
    """

    def __init__(self, model: str, max_tokens: int = 4000, retries: int = 3,
                 rpm_limit: int = 14):
        # rpm_limit: stay at 14 instead of 15 to give a 1-request safety margin
        from google import genai

        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "No Gemini API key found. Set GEMINI_API_KEY in your .env file.\n"
                "Get a free key at: https://aistudio.google.com/apikey"
            )

        self._genai = genai
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.retries = retries
        self._rate_limiter = RateLimiter(max_calls=rpm_limit, window_seconds=60.0)

    def complete_json(self, system: str, user: str, task: str = ""):
        """Call Gemini and return parsed JSON.

        Automatically throttles to stay within the free-tier 15 RPM limit.
        Retries on transient errors with exponential back-off.
        """
        from google.genai import types

        # Combine system + user into a single prompt
        full_prompt = f"{system}\n\n{user}" if system else user

        config = types.GenerateContentConfig(
            max_output_tokens=self.max_tokens,
            temperature=0.2,                      # low temp → consistent JSON
            response_mime_type="application/json",
        )

        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                # --- Wait here if we're at the rate limit ---
                self._rate_limiter.wait()
                # -------------------------------------------

                response = self.client.models.generate_content(
                    model=self.model,
                    contents=full_prompt,
                    config=config,
                )
                return parse_json(response.text)

            except (ValueError, json.JSONDecodeError) as e:
                last = e
                time.sleep(2 ** attempt)   # 1s, 2s, 4s
            except Exception as e:
                last = e
                # On quota errors specifically, back off longer
                msg = str(e).lower()
                if "quota" in msg or "429" in msg or "rate" in msg:
                    wait = 60 + 2 ** attempt   # give the quota window time to reset
                    print(f"[rate-limit] quota hit on attempt {attempt+1}, sleeping {wait}s...")
                    time.sleep(wait)
                else:
                    time.sleep(2 ** attempt)

        raise RuntimeError(f"LLM call failed for task '{task}': {last}")

"""
EG2A17 - Fall / Slip-Trip-Fall / Near-Miss detection engine
============================================================
This is the CORE of the project: it turns a stream of IMU samples into
safety EVENTS. It works both live (fed sample-by-sample) and offline
(replayed over stored data), so the same tested logic is used everywhere.

How it works -- a small state machine over acceleration magnitude:

  Normal life sits near 1 g (gravity).

  A genuine FALL has a recognisable 3-phase signature:
    1. FREE FALL  -> magnitude drops toward 0 g (body accelerating down)
    2. IMPACT     -> sharp spike well above 1 g (hitting the ground)
    3. STILLNESS  -> unusual quiet afterwards (person motionless)

  A NEAR MISS (trip but recovered) shows a big gyroscope spike and/or an
  impact-like jolt, but is NOT followed by stillness -- the worker keeps
  moving. That absence of post-impact stillness is what separates a scary
  stumble from an actual fall.

Severity is graded from the peak impact magnitude.

Thresholds live in config.py -- tune them with YOUR recorded data and
write the final chosen values (and why) into your report.
"""

import math
import config


def magnitude(x, y, z):
    return math.sqrt(x * x + y * y + z * z)


class FallDetector:
    # internal states
    NORMAL = "NORMAL"
    FREEFALL = "FREEFALL"
    IMPACT_WAIT = "IMPACT_WAIT"   # saw freefall, waiting for impact
    POST_IMPACT = "POST_IMPACT"   # saw impact, checking for stillness

    REFRACTORY_S = 1.0   # ignore new detections for this long after an event
                         # (long enough to stop one incident double-firing,
                         #  short enough that back-to-back demo events register)

    def __init__(self, sample_rate_hz=None):
        self.rate = sample_rate_hz or config.SAMPLE_RATE_HZ
        self.dt = 1.0 / self.rate
        self.state = self.NORMAL
        self.timer = 0.0            # seconds spent in current phase
        self.peak_g = 0.0
        self.still_time = 0.0       # how long the person has been still
        self.cooldown = 0.0         # seconds remaining in refractory period

    def _severity(self, peak):
        if peak >= 4.0:
            return "HIGH"
        if peak >= 3.0:
            return "MED"
        return "LOW"

    def update(self, ax, ay, az, gx, gy, gz):
        """
        Feed one sample. Returns an event dict if one was detected on this
        sample, otherwise None. Event dict:
            {"type": "FALL"|"STF"|"NEAR_MISS", "severity": str, "peak_g": float}
        """
        # During the refractory period after an event, swallow everything so
        # one physical incident produces exactly one detection.
        if self.cooldown > 0.0:
            self.cooldown -= self.dt
            return None

        acc_mag = magnitude(ax, ay, az)
        gyr_mag = magnitude(gx, gy, gz)
        deviation = abs(acc_mag - 1.0)   # how far from resting gravity

        # ---- Near miss can fire from any non-fall state: a big rotational
        #      lurch that doesn't become a full fall (checked at the end) ----
        near_miss_spike = gyr_mag >= config.NEARMISS_GYR

        # ---------------- STATE MACHINE ----------------
        if self.state == self.NORMAL:
            if acc_mag < config.FREEFALL_G:
                # Entering possible free fall takes priority over near-miss.
                self.state = self.FREEFALL
                self.timer = 0.0
                self.peak_g = 0.0
            elif near_miss_spike:
                # A rotational lurch while NOT in free fall. To stop a drop's
                # spin from being logged as a near-miss before its free-fall
                # phase develops, require the acceleration to be near-normal
                # (i.e. the device is upright/level, not already falling).
                if abs(acc_mag - 1.0) < 0.5:
                    return self._emit_near_miss(gyr_mag)

        elif self.state == self.FREEFALL:
            self.timer += self.dt
            if acc_mag >= config.IMPACT_G:
                # freefall immediately followed by impact
                self.state = self.POST_IMPACT
                self.timer = 0.0
                self.peak_g = acc_mag
                self.still_time = 0.0
            elif self.timer > config.FALL_WINDOW_S:
                # freefall didn't lead to impact in time -> abort
                self.state = self.NORMAL

        elif self.state == self.POST_IMPACT:
            self.timer += self.dt
            self.peak_g = max(self.peak_g, acc_mag)
            if deviation < config.STILL_G_BAND:
                self.still_time += self.dt
            else:
                self.still_time = 0.0
            # confirmed fall: stayed still long enough after impact
            if self.still_time >= config.POST_IMPACT_S:
                return self._emit_fall(self.peak_g)
            # if they got up and moved again quickly -> treat as near miss
            if self.timer > (config.POST_IMPACT_S + 1.0):
                return self._emit_near_miss(self.peak_g, from_impact=True)

        return None

    # ---- event emitters (also reset the machine) ----
    def _emit_fall(self, peak):
        self._reset()
        # Distinguish FFH vs STF is hard from IMU alone; we label big-impact
        # falls FALL and lighter ones STF. Documented simplification.
        etype = "FALL" if peak >= 3.5 else "STF"
        # For falls the peak is an acceleration magnitude, measured in g.
        return {"type": etype, "severity": self._severity(peak),
                "peak": round(peak, 2), "unit": "g"}

    def _emit_near_miss(self, peak, from_impact=False):
        self._reset()
        # For a near miss driven by rotation the peak is an angular rate in
        # deg/s (dps), NOT a g-force. If it came from a post-impact recovery
        # the peak is a g value. Label accordingly so screens/reports are
        # not showing an impossible "800 g".
        unit = "g" if from_impact else "dps"
        return {"type": "NEAR_MISS", "severity": "LOW",
                "peak": round(peak, 2), "unit": unit}

    def _reset(self):
        self.state = self.NORMAL
        self.timer = 0.0
        self.peak_g = 0.0
        self.still_time = 0.0
        self.cooldown = self.REFRACTORY_S
import os
import time
import logging
import threading
from typing import List, Optional

from octoeverywhere.sentry import Sentry
from octoeverywhere.gadget import Gadget
from octoeverywhere.httpsessions import HttpSessions

from .moonrakerclient import MoonrakerClient


# Writes a small Gadget status image into the Klipper config folder.
# Fluidd and Mainsail can show it as a webcam using the adaptive MJPEG service, which reloads the image,
# so the user gets a live Gadget status card without anything in the frontend being changed.
class GadgetStatusCard:

    # The image is written to config/.octoeverywhere/gadget-status.svg
    # Moonraker serves it at /server/files/config/.octoeverywhere/gadget-status.svg
    c_FolderName = ".octoeverywhere"
    c_FileName = "gadget-status.svg"

    c_Width = 320
    c_Height = 180


    # In companion mode there's no config folder, so configFolderPath is None and the image is uploaded through Moonraker.
    def __init__(self, logger:logging.Logger, gadget:Gadget, configFolderPath:Optional[str]) -> None:
        self.Logger = logger
        self.Gadget = gadget
        self.FolderPath:Optional[str] = None
        self.FilePath:Optional[str] = None
        if configFolderPath is not None:
            self.FolderPath = os.path.join(configFolderPath, GadgetStatusCard.c_FolderName)
            self.FilePath = os.path.join(self.FolderPath, GadgetStatusCard.c_FileName)
        self.Lock = threading.Lock()


    def Start(self) -> None:
        if self.FilePath is not None:
            self.Logger.info("Gadget status card enabled, writing to "+self.FilePath)
        else:
            self.Logger.info("Gadget status card enabled, uploading through Moonraker")
        self.Gadget.SetStatusChangedCallback(self._OnStatusChanged)
        # Write the initial card, so the frontend has something to show.
        self._OnStatusChanged()


    # Called by Gadget when it starts or stops watching, or gets a new result from the server.
    def _OnStatusChanged(self) -> None:
        try:
            with self.Lock:
                self._Write(self._Render())
        except Exception as e:
            Sentry.OnException("GadgetStatusCard failed to update the status image.", e)


    def _Write(self, svg:str) -> None:
        if self.FolderPath is None or self.FilePath is None:
            self._Upload(svg)
            return
        os.makedirs(self.FolderPath, exist_ok=True)
        # Write to a temp file and swap it in, so the frontend never loads a half written image.
        tempPath = self.FilePath + ".tmp"
        with open(tempPath, "w", encoding="utf-8") as f:
            f.write(svg)
        os.replace(tempPath, self.FilePath)


    # Used in companion mode, uploads the image into the config folder with the Moonraker file API.
    def _Upload(self, svg:str) -> None:
        client = MoonrakerClient.Get()
        url = "http://" + client.MoonrakerHostAndPort + "/server/files/upload"
        headers = {}
        if client.MoonrakerApiKey is not None and len(client.MoonrakerApiKey) > 0:
            headers["X-Api-Key"] = client.MoonrakerApiKey
        try:
            r = HttpSessions.GetSession(url).post(url,
                    data={"root": "config", "path": GadgetStatusCard.c_FolderName},
                    files={"file": (GadgetStatusCard.c_FileName, svg.encode("utf-8"), "image/svg+xml")},
                    headers=headers,
                    timeout=10)
            if r.status_code < 200 or r.status_code >= 300:
                self.Logger.warning(f"GadgetStatusCard failed to upload the status image, Moonraker returned {r.status_code}")
        except Exception as e:
            # This is expected if Moonraker isn't reachable right now, the next status change will try again.
            self.Logger.warning("GadgetStatusCard failed to upload the status image. "+str(e))


    def _Render(self) -> str:
        g = self.Gadget
        history = g.GetScoreHistoryFloats()
        hasScore = len(history) > 0
        warnTimeSec = self._TimeOrNone(g.GetTimeOrNoneSinceLastWarningIntSec())
        pauseTimeSec = self._TimeOrNone(g.GetTimeOrNoneSinceLastPauseIntSec())

        # Pick the status line and its color.
        if g.IsPrintSuppressed():
            status, color = "Off for this print", "#9e9e9e"
        elif pauseTimeSec is not None:
            status, color = "Paused print at " + self._Clock(pauseTimeSec), "#f44336"
        elif warnTimeSec is not None:
            status, color = "Warning sent at " + self._Clock(warnTimeSec), "#ff9800"
        elif g.IsWatching():
            status, color = "Watching", "#4caf50"
        else:
            status, color = "Not printing", "#9e9e9e"

        scoreText = f"{g.GetLastGadgetScoreFloat() * 100:.0f}%" if hasScore else "--"
        checkText = "No checks yet"
        if hasScore:
            checkText = "Last check " + self._Clock(time.time() - g.GetLastTimeSinceScoreUpdateSecFloat())

        w = GadgetStatusCard.c_Width
        h = GadgetStatusCard.c_Height
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<rect width="{w}" height="{h}" fill="#1e1e1e"/>'
            '<text x="16" y="30" font-family="sans-serif" font-size="18" font-weight="bold" fill="#ffffff">Gadget</text>'
            f'<circle cx="{w - 24}" cy="24" r="8" fill="{color}"/>'
            f'<text x="16" y="56" font-family="sans-serif" font-size="14" fill="{color}">{status}</text>'
            f'<text x="16" y="104" font-family="sans-serif" font-size="40" font-weight="bold" fill="#ffffff">{scoreText}</text>'
            '<text x="16" y="124" font-family="sans-serif" font-size="12" fill="#9e9e9e">score</text>'
            f'{self._Sparkline(history, 140, 70, w - 156, 60)}'
            f'<text x="16" y="{h - 16}" font-family="sans-serif" font-size="12" fill="#9e9e9e">{checkText}</text>'
            '</svg>'
        )


    # Draws the score history as a small line graph, oldest on the left.
    def _Sparkline(self, history:List[float], x:int, y:int, width:int, height:int) -> str:
        box = f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="none" stroke="#333333"/>'
        if len(history) < 2:
            return box
        values = list(reversed(history))
        step = width / (len(values) - 1)
        points = " ".join(f"{x + i * step:.1f},{y + height - max(0.0, min(1.0, v)) * height:.1f}" for i, v in enumerate(values))
        return box + f'<polyline points="{points}" fill="none" stroke="#2196f3" stroke-width="2"/>'


    # Gadget gives us seconds since something happened, convert it to the time it happened.
    def _TimeOrNone(self, secondsSince:Optional[int]) -> Optional[float]:
        if secondsSince is None:
            return None
        return time.time() - secondsSince


    def _Clock(self, timeSec:float) -> str:
        return time.strftime("%H:%M:%S", time.localtime(timeSec))

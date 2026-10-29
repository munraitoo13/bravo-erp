"""Deterministic CCTV bitrate lookup table (kbps) across Resolution x FPS x Codec."""

from src.core.exceptions import DomainValidationError
from src.modules.sizing.domain.value_objects import CodecLiteral, FpsLiteral, ResolutionLiteral

type BitrateKey = tuple[ResolutionLiteral, FpsLiteral, CodecLiteral]

# Deterministic bitrate matrix (kbps) matching SPEC.md Section 3.1.A
BITRATE_LOOKUP_KBPS: dict[BitrateKey, int] = {
    # 720p (1 MP)
    ("720p", 15, "H.264"): 1024,
    ("720p", 15, "H.265"): 563,
    ("720p", 15, "H.265+"): 358,
    ("720p", 20, "H.264"): 1365,
    ("720p", 20, "H.265"): 751,
    ("720p", 20, "H.265+"): 478,
    ("720p", 30, "H.264"): 2048,
    ("720p", 30, "H.265"): 1126,
    ("720p", 30, "H.265+"): 717,
    # 1080p (2 MP)
    ("1080p", 15, "H.264"): 2048,
    ("1080p", 15, "H.265"): 1126,
    ("1080p", 15, "H.265+"): 717,
    ("1080p", 20, "H.264"): 2731,
    ("1080p", 20, "H.265"): 1502,
    ("1080p", 20, "H.265+"): 956,
    ("1080p", 30, "H.264"): 4096,
    ("1080p", 30, "H.265"): 2253,
    ("1080p", 30, "H.265+"): 1434,
    # 4MP (2K)
    ("4MP", 15, "H.264"): 3072,
    ("4MP", 15, "H.265"): 1690,
    ("4MP", 15, "H.265+"): 1075,
    ("4MP", 20, "H.264"): 4096,
    ("4MP", 20, "H.265"): 2253,
    ("4MP", 20, "H.265+"): 1434,
    ("4MP", 30, "H.264"): 6144,
    ("4MP", 30, "H.265"): 3379,
    ("4MP", 30, "H.265+"): 2150,
    # 4K (8 MP)
    ("4K", 15, "H.264"): 5120,
    ("4K", 15, "H.265"): 2816,
    ("4K", 15, "H.265+"): 1792,
    ("4K", 20, "H.264"): 6827,
    ("4K", 20, "H.265"): 3755,
    ("4K", 20, "H.265+"): 2389,
    ("4K", 30, "H.264"): 10240,
    ("4K", 30, "H.265"): 5632,
    ("4K", 30, "H.265+"): 3584,
}


def get_bitrate_kbps(
    resolution: ResolutionLiteral,
    fps: FpsLiteral,
    codec: CodecLiteral,
) -> int:
    """Return exact stream bitrate in kbps for a (resolution, fps, codec) tuple."""
    key: BitrateKey = (resolution, fps, codec)
    if key not in BITRATE_LOOKUP_KBPS:
        raise DomainValidationError(
            detail=(
                f"Unsupported bitrate combination: resolution={resolution}, "
                f"fps={fps}, codec={codec}."
            ),
            errors=[
                {
                    "resolution": resolution,
                    "fps": fps,
                    "codec": codec,
                }
            ],
        )
    return BITRATE_LOOKUP_KBPS[key]

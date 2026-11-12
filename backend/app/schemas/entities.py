from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    mode: str = Field(default="incremental", pattern="^(incremental|full)$")


class LookbackUpdate(BaseModel):
    lookback_seconds: int = Field(ge=0, le=86400 * 30)


class SettingUpdate(BaseModel):
    value: str


class ExportRuleUpdate(BaseModel):
    mask_type: str = Field(pattern="^(none|keep_edges|blank|hash)$")
    keep_head: int = Field(default=0, ge=0, le=64)
    keep_tail: int = Field(default=0, ge=0, le=64)

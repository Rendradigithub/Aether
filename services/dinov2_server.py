import base64
import io
import os
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import numpy as np
from PIL import Image, UnidentifiedImageError
import torch
import torchvision.transforms as T
import uvicorn

app = FastAPI(
    title="Aether DINOv2 Perception Node",
    description="Microservice inferensi visual DINOv2 untuk RemotePerceptionEncoder Aether.",
    version="1.0.0",
)

API_KEY = os.getenv("DINOV2_API_KEY", None)
security = HTTPBearer(auto_error=False)


def verify_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
):
    if API_KEY is None:
        return True
    if not credentials or credentials.credentials != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True


device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"[DINOv2 Server] Menggunakan device: {device}")

print("[DINOv2 Server] Memuat bobot dinov2_vits14 dari facebookresearch/dinov2...")
model = torch.hub.load("facebookresearch/dinov2", "dinov2_vits14")
model.to(device)
model.eval()
print("[DINOv2 Server] Model berhasil dimuat ke memori.")

transform = T.Compose(
    [
        T.Resize(256, interpolation=T.InterpolationMode.BICUBIC),
        T.CenterCrop(224),
        T.ToTensor(),
        T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ]
)


@app.get("/health")
def health_check():
    return {
        "status": "online",
        "model": "dinov2_vits14",
        "embedding_dim": 384,
        "device": str(device),
        "auth_enabled": API_KEY is not None,
    }


@app.post("/encode")
async def encode_image(
    request: Request,
    authenticated: bool = Depends(verify_api_key),
):
    try:
        body = await request.json()
        
        # Ekstrak data_base64 sesuai kontrak RemotePerceptionEncoder Aether
        raw_b64 = body.get("data_base64") or body.get("image") or body.get("image_base64")
        if not raw_b64:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Field 'data_base64' tidak ditemukan dalam payload JSON.",
            )

        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]

        image_bytes = base64.b64decode(raw_b64)
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    except HTTPException:
        raise
    except UnidentifiedImageError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Data base64 tidak valid sebagai citra.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Gagal memproses request: {str(e)}",
        )

    # Preprocessing citra ke Tensor [1, 3, 224, 224]
    input_tensor = transform(image).unsqueeze(0).to(device)

    # Inferensi Feedforward DINOv2
    with torch.no_grad():
        embedding = model(input_tensor).squeeze(0).cpu().numpy().astype(np.float32)

    if not np.isfinite(embedding).all():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Inferensi menghasilkan nilai non-finite (NaN/Inf).",
        )

    # Return format yang diharapkan RemotePerceptionEncoder
    return {
        "embedding": embedding.tolist()
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
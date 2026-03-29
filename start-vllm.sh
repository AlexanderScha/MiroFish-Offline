#!/bin/bash
# Start vLLM server with tensor parallelism across both RTX 3090s
# Serves Qwen2.5-32B-Instruct-AWQ on port 8000 (OpenAI-compatible API)
# Ollama continues to run on port 11434 for embeddings (nomic-embed-text)

set -e

echo "🚀 Starting vLLM server (dual GPU, tensor parallelism)"
echo "=================================================="

source ~/miniconda3/bin/activate mirofish

# Verify both GPUs are available
GPU_COUNT=$(python3 -c "import torch; print(torch.cuda.device_count())")
echo "GPUs detected: $GPU_COUNT"

if [ "$GPU_COUNT" -lt 2 ]; then
    echo "⚠️  Only $GPU_COUNT GPU(s) detected. Using TP=1 (single GPU mode)"
    TP_SIZE=1
else
    echo "✓ Both GPUs available. Using TP=2 (tensor parallel)"
    TP_SIZE=2
fi

echo ""
echo "Model: Qwen/Qwen2.5-32B-Instruct-AWQ"
echo "Port: 8000"
echo "Tensor Parallel: $TP_SIZE"
echo "Max concurrent sequences: 16"
echo "=================================================="
echo ""

python3 -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-32B-Instruct-AWQ \
    --tensor-parallel-size $TP_SIZE \
    --max-num-seqs 16 \
    --max-model-len 16384 \
    --gpu-memory-utilization 0.85 \
    --port 8000 \
    --host 0.0.0.0 \
    --served-model-name "qwen2.5:32b" \
    --trust-remote-code \
    --no-enable-log-requests \
    --quantization awq \
    --enable-auto-tool-choice \
    --tool-call-parser hermes \
    2>&1 | tee logs/vllm.log

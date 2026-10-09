package com.hivision.idphotos

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.io.File
import java.io.FileOutputStream
import java.nio.FloatBuffer
import kotlin.math.exp
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * 人像抠图引擎：忠实移植 desktop/server.py 走的 hivision birefnet 路径
 * （hivision/creator/human_matting.py::get_birefnet_portrait_matting）：
 *   输入图直接缩放到 1024×1024（双线性，允许拉伸变形，与桌面版保持一致）；
 *   ImageNet mean/std 归一化；输出 logits 做 sigmoid 得 alpha；
 *   alpha 双线性放回原图尺寸。
 *
 * 合成底色用逐像素线性插值（与 hivision/utils.py::add_background 的 a/255 混合同数学），
 * 不经过 Bitmap xfermode，避免 premultiplied 等平台行为差异。
 */
class MattingEngine(private val context: Context) {

    /** 抠图+合成结果：composited 为合成底色图，cutout 为透明底 RGBA 图，bgAlphaPct 为四角背景 alpha 均值。 */
    class MatteOutput(
        val composited: Bitmap,
        val cutout: Bitmap,
        val bgAlphaPct: Int,
    )

    private val env: OrtEnvironment = OrtEnvironment.getEnvironment()
    private var session: OrtSession? = null
    private val lock = Any()

    private fun ensureSession(): OrtSession {
        session?.let { return it }
        synchronized(lock) {
            session?.let { return it }
            // 模型从 assets 复制到应用私有目录（仅首次启动一次性开销）
            val f = File(context.filesDir, MODEL_FILE)
            if (!f.exists() || f.length() < MODEL_BYTES_MIN) {
                context.assets.open(MODEL_FILE).use { input ->
                    FileOutputStream(f).use { output -> input.copyTo(output) }
                }
            }
            // 优先 XNNPACK 加速（ARM CPU 上 FP32 通常 1.5~2 倍），失败则回退纯 CPU 4 线程
            session = try {
                val opts = OrtSession.SessionOptions().apply {
                    setIntraOpNumThreads(1) // XNNPACK 自带线程池，全局线程数须为 1
                    addXnnpack(mapOf("intra_op_num_threads" to "4"))
                }
                env.createSession(f.absolutePath, opts)
            } catch (e: Throwable) {
                val opts = OrtSession.SessionOptions().apply { setIntraOpNumThreads(4) }
                env.createSession(f.absolutePath, opts)
            }
            return session!!
        }
    }

    /** 输入原图与底色，返回合成结果、透明底抠图和背景 alpha 诊断值。 */
    fun matte(original: Bitmap, bgColor: Int): MatteOutput {
        val src = if (original.config == Bitmap.Config.ARGB_8888) original
        else original.copy(Bitmap.Config.ARGB_8888, false)

        val session = ensureSession()
        val inputName = session.inputNames.iterator().next()

        // 1) 缩放到 1024×1024（与 PIL resize 双线性一致）
        val input = Bitmap.createScaledBitmap(src, SIDE, SIDE, true)
        val pixels = IntArray(SIDE * SIDE)
        input.getPixels(pixels, 0, SIDE, 0, 0, SIDE, SIDE)

        // 2) NCHW + ImageNet 归一化
        val area = SIDE * SIDE
        val chw = FloatArray(3 * area)
        val mean = floatArrayOf(0.485f, 0.456f, 0.406f)
        val std = floatArrayOf(0.229f, 0.224f, 0.225f)
        for (i in 0 until area) {
            val p = pixels[i]
            chw[i] = (((p shr 16) and 0xFF) / 255f - mean[0]) / std[0]
            chw[area + i] = (((p shr 8) and 0xFF) / 255f - mean[1]) / std[1]
            chw[2 * area + i] = ((p and 0xFF) / 255f - mean[2]) / std[2]
        }

        // 3) 推理 + sigmoid
        val alpha1024 = FloatArray(area)
        OnnxTensor.createTensor(env, FloatBuffer.wrap(chw), longArrayOf(1, 3, SIDE.toLong(), SIDE.toLong())).use { tensor ->
            session.run(mapOf(inputName to tensor)).use { result ->
                val out = result[0] as OnnxTensor
                val logits = out.floatBuffer
                for (i in 0 until area) {
                    alpha1024[i] = 1f / (1f + exp(-logits.get(i)))
                }
            }
        }

        // 4) 双线性把 alpha 放回原图尺寸，逐像素合成（与桌面版 add_background 同数学）
        val w = src.width
        val h = src.height
        val srcPixels = IntArray(w * h)
        src.getPixels(srcPixels, 0, w, 0, 0, w, h)
        val cutPixels = IntArray(w * h)
        val compPixels = IntArray(w * h)
        val br = Color.red(bgColor)
        val bgg = Color.green(bgColor)
        val bb = Color.blue(bgColor)
        val sx = (SIDE - 1).toFloat() / maxOf(1, w - 1)
        val sy = (SIDE - 1).toFloat() / maxOf(1, h - 1)

        for (y in 0 until h) {
            val fy = y * sy
            val y0 = fy.toInt()
            val y1 = min(y0 + 1, SIDE - 1)
            val ty = fy - y0
            val row0 = y0 * SIDE
            val row1 = y1 * SIDE
            var outIdx = y * w
            for (x in 0 until w) {
                val fx = x * sx
                val x0 = fx.toInt()
                val x1 = min(x0 + 1, SIDE - 1)
                val tx = fx - x0
                val aTop = alpha1024[row0 + x0] * (1 - tx) + alpha1024[row0 + x1] * tx
                val aBot = alpha1024[row1 + x0] * (1 - tx) + alpha1024[row1 + x1] * tx
                val aF = aTop * (1 - ty) + aBot * ty
                val a = (aF * 255f + 0.5f).roundToInt().coerceIn(0, 255)

                val p = srcPixels[outIdx]
                val r = (p shr 16) and 0xFF
                val g = (p shr 8) and 0xFF
                val b = p and 0xFF
                cutPixels[outIdx] = Color.argb(a, r, g, b)
                compPixels[outIdx] = Color.rgb(
                    (r * a + br * (255 - a) + 127) / 255,
                    (g * a + bgg * (255 - a) + 127) / 255,
                    (b * a + bb * (255 - a) + 127) / 255,
                )
                outIdx++
            }
        }

        return MatteOutput(
            composited = Bitmap.createBitmap(compPixels, w, h, Bitmap.Config.ARGB_8888),
            cutout = Bitmap.createBitmap(cutPixels, w, h, Bitmap.Config.ARGB_8888),
            bgAlphaPct = cornerAlphaPct(alpha1024),
        )
    }

    /** 顶部两角 64×64 区域的 alpha 均值（0-100）。证件照人像头部不会占据画面顶角，
     *  该处应接近 0；注意画面下半部分的"四角"常是人物身体，不能算背景。 */
    private fun cornerAlphaPct(alpha: FloatArray): Int {
        val box = 64
        var sum = 0.0
        var count = 0
        for (cx in intArrayOf(0, SIDE - box)) {
            for (y in 0 until box) {
                for (x in cx until cx + box) {
                    sum += alpha[y * SIDE + x]
                    count++
                }
            }
        }
        return if (count == 0) 0 else ((sum / count) * 100).roundToInt()
    }

    companion object {
        private const val MODEL_FILE = "birefnet-v1-lite.onnx"
        private const val MODEL_BYTES_MIN = 200L * 1024 * 1024
        private const val SIDE = 1024
    }
}

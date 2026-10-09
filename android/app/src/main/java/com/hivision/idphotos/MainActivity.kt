package com.hivision.idphotos

import android.content.ContentValues
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ImageDecoder
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.MediaStore
import android.util.Log
import android.widget.Button
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import java.io.File
import java.util.concurrent.Executors
import kotlin.math.max
import kotlin.math.roundToInt

class MainActivity : ComponentActivity() {

    private lateinit var preview: ImageView
    private lateinit var status: TextView
    private lateinit var btnPick: Button
    private lateinit var btnGo: Button

    private val executor = Executors.newSingleThreadExecutor()
    private val engine by lazy { MattingEngine(this) }
    private var picked: Bitmap? = null

    private val pickMedia =
        registerForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
            if (uri != null) {
                val bmp = loadDownscaled(uri, MAX_SIDE)
                if (bmp == null) {
                    setStatus("读取失败（${lastError ?: "未知原因"}）请截图反馈", true)
                } else {
                    picked = bmp
                    preview.setImageBitmap(bmp)
                    btnGo.isEnabled = true
                    setStatus("已选图 ${bmp.width}×${bmp.height}，点击生成（蓝底一寸）")
                }
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        preview = findViewById(R.id.preview)
        status = findViewById(R.id.status)
        btnPick = findViewById(R.id.btnPick)
        btnGo = findViewById(R.id.btnGo)

        btnPick.setOnClickListener {
            pickMedia.launch(
                PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)
            )
        }
        btnGo.setOnClickListener { generate() }
    }

    private fun generate() {
        val src = picked ?: return
        btnGo.isEnabled = false
        btnPick.isEnabled = false
        setStatus("生成中…（首次启动要复制 224MB 模型 + 加载，最久约 1 分钟）")
        executor.execute {
            try {
                val t0 = System.currentTimeMillis()
                val out = engine.matte(src, Color.parseColor("#638cce"))
                val seconds = (System.currentTimeMillis() - t0) / 1000.0
                runOnUiThread {
                    preview.setImageBitmap(out.composited)
                    val where = saveToGallery(out.composited)
                    setStatus(
                        "完成（${"%.1f".format(seconds)} 秒，背景alpha=${out.bgAlphaPct}%）已保存到 $where"
                    )
                }
            } catch (e: Throwable) {
                runOnUiThread { setStatus("失败：${e.message}", true) }
            } finally {
                runOnUiThread {
                    btnGo.isEnabled = true
                    btnPick.isEnabled = true
                }
            }
        }
    }

    /** 优先存入系统相册 Pictures/HivisionIDPhotos；旧机型存应用目录并提示路径。 */
    private fun saveToGallery(bmp: Bitmap): String {
        val name = "IDPhoto_" + System.currentTimeMillis() + ".png"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val values = ContentValues().apply {
                put(MediaStore.Images.Media.DISPLAY_NAME, name)
                put(MediaStore.Images.Media.MIME_TYPE, "image/png")
                put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/HivisionIDPhotos")
            }
            val uri: Uri = contentResolver.insert(
                MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values
            ) ?: throw IllegalStateException("无法创建相册文件")
            contentResolver.openOutputStream(uri)?.use {
                bmp.compress(Bitmap.CompressFormat.PNG, 100, it)
            }
            return "相册 Pictures/HivisionIDPhotos"
        } else {
            val dir = File(getExternalFilesDir(null), "HivisionIDPhotos").apply { mkdirs() }
            val f = File(dir, name)
            f.outputStream().use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
            Toast.makeText(this, "已保存：$f", Toast.LENGTH_LONG).show()
            return f.absolutePath
        }
    }

    /** 解码系统相册图，最长边压到 MAX_SIDE（与桌面版 resize_image_esp(2000) 对应）。 */
    private var lastError: String? = null

    private fun loadDownscaled(uri: Uri, maxSide: Int): Bitmap? {
        lastError = null
        val src = try {
            decodeBitmap(uri)
        } catch (t: Throwable) {
            Log.e("MainActivity", "decode failed: $uri", t)
            lastError = t.javaClass.simpleName + ": " + (t.message ?: "").take(80)
            null
        }
        if (src == null) {
            if (lastError == null) lastError = "解码返回空（格式不支持？）"
            return null
        }
        val scale = maxSide.toFloat() / max(src.width, src.height)
        return if (scale < 1f) {
            Bitmap.createScaledBitmap(
                src,
                (src.width * scale).roundToInt(),
                (src.height * scale).roundToInt(),
                true,
            )
        } else src
    }

    /** Android 9+ 用 ImageDecoder（原生支持 HEIF/AVIF 等新格式，强制软件位图供像素读取）；
     *  解码时按 MAX_SIDE 降采样（避免大图全尺寸解码 OOM）；Android 8.x 走 BitmapFactory 两段式。 */
    private fun decodeBitmap(uri: Uri): Bitmap? {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            val source = ImageDecoder.createSource(contentResolver, uri)
            ImageDecoder.decodeBitmap(source) { decoder, info, _ ->
                val maxDim = max(info.size.width, info.size.height)
                var sample = 1
                while (maxDim / (sample * 2) >= MAX_SIDE) sample *= 2
                if (sample > 1) decoder.setTargetSampleSize(sample)
                decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
                decoder.isMutableRequired = true
            }
        } else {
            val bounds = android.graphics.BitmapFactory.Options().apply { inJustDecodeBounds = true }
            contentResolver.openInputStream(uri)?.use {
                android.graphics.BitmapFactory.decodeStream(it, null, bounds)
            } ?: return null
            if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null
            var sample = 1
            while (max(bounds.outWidth, bounds.outHeight) / (sample * 2) >= MAX_SIDE) sample *= 2
            val opts = android.graphics.BitmapFactory.Options().apply {
                inSampleSize = sample
                inPreferredConfig = Bitmap.Config.ARGB_8888
            }
            contentResolver.openInputStream(uri)?.use {
                android.graphics.BitmapFactory.decodeStream(it, null, opts)
            } ?: return null
        }
    }

    private fun setStatus(msg: String, isError: Boolean = false) {
        runOnUiThread {
            status.text = msg
            status.setTextColor(if (isError) 0xFFCC3333.toInt() else 0xFF333333.toInt())
        }
    }

    companion object {
        private const val MAX_SIDE = 2000
    }
}

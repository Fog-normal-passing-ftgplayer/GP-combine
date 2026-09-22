package com.gpcombine.assistant.store

import android.content.Context

/** 记住上次连的设备和配对码，省得每次重输。M1 只存这两个，够用就行。 */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("gpcombine", Context.MODE_PRIVATE)

    var lastAddress: String?
        get() = sp.getString("lastAddress", null)
        set(v) = sp.edit().putString("lastAddress", v).apply()

    var pairCode: String?
        get() = sp.getString("pairCode", null)
        set(v) = sp.edit().putString("pairCode", v).apply()

    /** 诊断页解锁状态：连点 5 次版本号才置位，置位后一直有效（不然每次开 App 都要再点 5 下）。 */
    var diagUnlocked: Boolean
        get() = sp.getBoolean("diagUnlocked", false)
        set(v) = sp.edit().putBoolean("diagUnlocked", v).apply()
}

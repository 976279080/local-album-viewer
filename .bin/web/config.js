/**
 * 前端配置文件
 * 通过 script 标签同步加载，全局变量 window.APP_CONFIG 在 Vue 应用启动前可用
 *
 * 修改配置后刷新页面即可生效，无需重启服务
 * 所有读取处均使用 window.APP_CONFIG?.xxx ?? defaultValue 兜底，删除本文件也不会崩溃
 */
window.APP_CONFIG = {
    // ========== 媒体处理 ==========
    media: {
        thumbnailMaxSize: 400,        // 缩略图高度像素（3:4竖图，宽度自动=高度*0.75）
        webpQuality: 0.93,            // WebP 压缩质量（0-1）
        batchSize: 5,                 // 同时处理的任务数
        maxMemoryMB: 500,             // 最大内存使用（MB）
        imageMaxSizeMB: 500,           // 图片跳过缩略图阈值（MB）
        videoMaxSizeMB: 5500,          // 视频跳过缩略图阈值（MB）
        singleFileMemoryLimitMB: 1000  // 单文件内存检查阈值（MB）
    },

    // ========== 重试策略 ==========
    retry: {
        summaryRetries: 10,          // summary 接口重试次数
        homeInitRetries: 15,         // home-init 接口重试次数
        intervalMs: 200              // 重试间隔（ms）
    },

    // ========== UI 行为 ==========
    ui: {
        notificationDurationMs: 2500, // 通知显示时间（ms）
        albumNameMaxLength: 15,       // 相册名最大长度
        renameAlbumMaxLength: 15,     // 重命名相册最大长度
        defaultAlbumColor: '#667eea'  // 默认相册颜色
    },

    // ========== 上传 ==========
    upload: {
        batchSize: 5,           // 上传批量大小
        timeoutMs: 120000       // 上传超时时间（ms）
    },

    // ========== 输入校验 ==========
    validation: {
        illegalChars: '\\/:*?"<>|.',     // 文件名非法字符（包括 . ）
        commentIllegalChars: '\\/:*?"<>|' // 评论非法字符（不允许 . ）
    },

    // ========== 文件类型 ==========
    fileTypes: {
        videoExtensions: ['mp4', 'mov', 'avi', 'mkv', 'wmv', 'flv', 'm4v', '3gp']
    },

    // ========== 评分系统 ==========
    rating: {
        levels: [
            { val: 2, label: '超爱' },
            { val: 1, label: '喜欢' },
            { val: 0, label: '一般' },
            { val: -1, label: '无感' }
        ]
    },

    // ========== API 路径 ==========
    api: {
        summary: '/api/summary',
        homeInit: '/api/home-init',
        albumInit: '/api/album-init',
        photo: '/api/photo',
        update: '/api/update',
        comment: '/api/comments',
        commentAdd: '/api/comments/add',
        commentDelete: '/api/comments/delete',
        delete: '/api/delete',
        batchTag: '/api/batch-tag',
        batchDelete: '/api/batch-delete',
        batchClearTags: '/api/batch-clear-tags',
        upload: '/api/upload',
        renameAlbum: '/api/rename-album'
    },

    // ========== 认证 ==========
    auth: {
        passwordStorageKey: 'password'  // sessionStorage 中密码的 key 名（密码本身保存在后端 config.py）
    }
};

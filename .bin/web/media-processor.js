/**
 * 前端媒体处理模块
 * 处理图片和视频的元数据获取、缩略图生成
 */

class MediaProcessor {
    static THUMBNAIL_MAX_SIZE = window.APP_CONFIG?.media?.thumbnailMaxSize ?? 500;
    static WEBP_QUALITY = window.APP_CONFIG?.media?.webpQuality ?? 0.95;
    static BATCH_SIZE = window.APP_CONFIG?.media?.batchSize ?? 5; // 同时处理的任务数
    static MAX_MEMORY_MB = window.APP_CONFIG?.media?.maxMemoryMB ?? 500; // 最大内存使用

    /**
     * 处理图片文件
     * @param {File} file - 图片文件
     * @returns {Promise<{width, height, createTime, thumbnail, thumbnailBlob}>}
     */
    static async processImage(file) {
        // HEIC 格式：浏览器无法直接解码，先用 heic2any 转为 JPEG
        const ext = MediaProcessor.getFileExtension(file.name);
        if (ext === '.heic') {
            return await this._processHeic(file);
        }

        return this._processNormalImage(file);
    }

    /**
     * 按需动态加载 heic2any 库（仅在遇到 HEIC 文件时加载）
     */
    static _heic2anyPromise = null;
    static loadHeic2any() {
        if (window.heic2any) return Promise.resolve(window.heic2any);
        if (this._heic2anyPromise) return this._heic2anyPromise;
        this._heic2anyPromise = new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = 'heic2any.min.js';
            script.onload = () => resolve(window.heic2any);
            script.onerror = () => {
                this._heic2anyPromise = null;
                reject(new Error('HEIC 解码库加载失败'));
            };
            document.head.appendChild(script);
        });
        return this._heic2anyPromise;
    }

    /**
     * 处理 HEIC 文件：动态加载 heic2any → 转 JPEG → 正常流程
     */
    static async _processHeic(file) {
        let createTime = this.getFileDate(file);
        try {
            createTime = await this.getExifDate(file);
        } catch (e) {
            console.warn('HEIC EXIF 解析失败，使用文件时间:', e.message);
        }

        try {
            // 按需加载 heic2any 库
            const heic2any = await this.loadHeic2any();
            const jpegBlob = await heic2any({ blob: file, toType: 'image/jpeg', quality: 0.9 });
            const jpegFile = new File([jpegBlob], file.name.replace(/\.heic$/i, '.jpg'), { type: 'image/jpeg' });

            // 用转换后的 JPEG 走正常图片处理流程
            const result = await this._processNormalImage(jpegFile);
            result.createTime = createTime;
            result.convertedFile = jpegFile;
            return result;
        } catch (err) {
            console.error('HEIC 转换失败:', err);
            return {
                width: 0,
                height: 0,
                createTime,
                thumbnail: null,
                thumbnailBlob: null,
                originalName: file.name
            };
        }
    }

    /**
     * 处理普通图片文件（PNG/JPEG/WebP 等）
     */
    static _processNormalImage(file) {
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.crossOrigin = 'anonymous';
            img.onload = async () => {
                try {
                    URL.revokeObjectURL(img.src);

                    const width = img.naturalWidth;
                    const height = img.naturalHeight;

                    let createTime = this.getFileDate(file);
                    try {
                        createTime = await this.getExifDate(file);
                    } catch (e) {
                        console.warn('EXIF 解析失败，使用文件时间:', e.message);
                    }

                    const { canvas, blob } = await this.generateThumbnail(img, 'image/webp');

                    resolve({
                        width,
                        height,
                        createTime,
                        thumbnail: canvas.toDataURL('image/webp', this.WEBP_QUALITY),
                        thumbnailBlob: blob,
                        originalName: file.name
                    });
                } catch (err) {
                    console.error('processImage 失败:', err);
                    resolve({
                        width: 0,
                        height: 0,
                        createTime: this.getFileDate(file),
                        thumbnail: null,
                        thumbnailBlob: null,
                        originalName: file.name
                    });
                }
            };

            img.onerror = () => {
                URL.revokeObjectURL(img.src);
                resolve({
                    width: 0,
                    height: 0,
                    createTime: this.getFileDate(file),
                    thumbnail: null,
                    thumbnailBlob: null,
                    originalName: file.name
                });
            };

            img.src = URL.createObjectURL(file);
        });
    }

    /**
     * 处理视频文件
     * @param {File} file - 视频文件
     * @returns {Promise<{width, height, createTime, thumbnail, thumbnailBlob}>}
     */
    static async processVideo(file) {
        // 并行解析 MP4 mvhd 的 creation_time（比 file.lastModified 更可靠，
        // 某些 App 处理后的视频 lastModified 会被错误设为 FILETIME 纪元 1601-01-01）
        const ext = this.getFileExtension(file.name);
        const mp4TimePromise = (ext === '.mp4' || ext === '.m4v' || ext === '.mov')
            ? this.getMp4CreationTime(file) : Promise.resolve(null);

        return new Promise((resolve, reject) => {
            const video = document.createElement('video');
            const url = URL.createObjectURL(file);
            let width, height, createTime;
            let resolved = false;

            video.preload = 'auto';
            video.muted = true;

            const timeoutId = setTimeout(() => {
                if (resolved) return;
                resolved = true;
                URL.revokeObjectURL(url);
                console.warn(`视频处理超时: ${file.name}`);
                resolve({
                    width: width || 0,
                    height: height || 0,
                    createTime: createTime || this.getFileDate(file),
                    thumbnail: null,
                    thumbnailBlob: null,
                    originalName: file.name
                });
            }, 30000);

            video.onloadedmetadata = () => {
                width = video.videoWidth;
                height = video.videoHeight;
                createTime = this.getFileDate(file);
                video.currentTime = 0.1;
            };

            video.onseeked = async () => {
                if (resolved) return;
                resolved = true;
                clearTimeout(timeoutId);

                try {
                    URL.revokeObjectURL(url);

                    const { canvas, blob } = await this.generateThumbnail(video, 'image/webp');

                    // 优先使用 MP4 mvhd 时间；若 mvhd 解析失败且 lastModified 异常（如 1601 年），回退到当前时间
                    let finalCreateTime = createTime;
                    try {
                        const mp4Time = await mp4TimePromise;
                        if (mp4Time && this._isReasonableDate(mp4Time)) {
                            finalCreateTime = mp4Time;
                        } else if (finalCreateTime && !this._isReasonableDate(finalCreateTime)) {
                            finalCreateTime = new Date().toISOString();
                        }
                    } catch (e) {
                        console.warn('MP4 时间解析异常:', e.message);
                    }

                    resolve({
                        width,
                        height,
                        createTime: finalCreateTime,
                        thumbnail: canvas.toDataURL('image/webp', this.WEBP_QUALITY),
                        thumbnailBlob: blob,
                        originalName: file.name
                    });
                } catch (err) {
                    console.error('processVideo 失败:', err);
                    resolve({
                        width: width || 0,
                        height: height || 0,
                        createTime: createTime || this.getFileDate(file),
                        thumbnail: null,
                        thumbnailBlob: null,
                        originalName: file.name
                    });
                }
            };

            video.onerror = () => {
                if (resolved) return;
                resolved = true;
                clearTimeout(timeoutId);

                URL.revokeObjectURL(url);
                resolve({
                    width: width || 0,
                    height: height || 0,
                    createTime: createTime || this.getFileDate(file),
                    thumbnail: null,
                    thumbnailBlob: null,
                    originalName: file.name
                });
            };

            video.src = url;
        });
    }

    /**
     * 生成缩略图
     * @param {HTMLImageElement|HTMLVideoElement} source - 图片或视频元素
     * @param {string} mimeType - 输出格式
     * @returns {Promise<{canvas, blob}>}
     */
    static async generateThumbnail(source, mimeType = 'image/webp') {
        return new Promise((resolve, reject) => {
            try {
                let sourceWidth, sourceHeight;
                
                if (source instanceof HTMLVideoElement) {
                    sourceWidth = source.videoWidth;
                    sourceHeight = source.videoHeight;
                } else {
                    sourceWidth = source.naturalWidth;
                    sourceHeight = source.naturalHeight;
                }
                
                const targetHeight = this.THUMBNAIL_MAX_SIZE;
                const targetWidth = Math.round(targetHeight * 3 / 4);
                
                const srcRatio = sourceWidth / sourceHeight;
                const targetRatio = 3 / 4;
                
                let sx, sy, sw, sh;
                if (srcRatio > targetRatio) {
                    sh = sourceHeight;
                    sw = Math.round(sh * targetRatio);
                    sx = Math.round((sourceWidth - sw) / 2);
                    sy = 0;
                } else {
                    sw = sourceWidth;
                    sh = Math.round(sw / targetRatio);
                    sx = 0;
                    sy = Math.round((sourceHeight - sh) / 2);
                }
                
                let curW = sw;
                let curH = sh;
                let curSource = source;
                let curSx = sx;
                let curSy = sy;
                
                const tempCanvases = [];
                
                while (curW > targetWidth * 2 && curH > targetHeight * 2) {
                    const nextW = Math.max(targetWidth, Math.floor(curW / 2));
                    const nextH = Math.max(targetHeight, Math.floor(curH / 2));
                    
                    const canvas = document.createElement('canvas');
                    canvas.width = nextW;
                    canvas.height = nextH;
                    const ctx = canvas.getContext('2d');
                    ctx.imageSmoothingEnabled = true;
                    ctx.imageSmoothingQuality = 'high';
                    
                    if (curSource === source) {
                        ctx.drawImage(curSource, curSx, curSy, curW, curH, 0, 0, nextW, nextH);
                    } else {
                        ctx.drawImage(curSource, 0, 0, curW, curH, 0, 0, nextW, nextH);
                    }
                    
                    tempCanvases.push(canvas);
                    curSource = canvas;
                    curW = nextW;
                    curH = nextH;
                    curSx = 0;
                    curSy = 0;
                }
                
                const canvas = document.createElement('canvas');
                const ctx = canvas.getContext('2d');
                
                canvas.width = targetWidth;
                canvas.height = targetHeight;
                
                ctx.imageSmoothingEnabled = true;
                ctx.imageSmoothingQuality = 'high';
                
                if (curSource === source) {
                    ctx.drawImage(curSource, curSx, curSy, curW, curH, 0, 0, targetWidth, targetHeight);
                } else {
                    ctx.drawImage(curSource, 0, 0, curW, curH, 0, 0, targetWidth, targetHeight);
                }
                
                canvas.toBlob((blob) => {
                    if (blob) {
                        resolve({ canvas, blob });
                    } else {
                        reject(new Error('缩略图生成失败'));
                    }
                }, mimeType, this.WEBP_QUALITY);
            } catch (err) {
                reject(err);
            }
        });
    }

    /**
     * 从图片文件获取 EXIF 日期
     * @param {File} file - 图片文件
     * @returns {Promise<string>} - ISO 日期字符串
     */
    static async getExifDate(file) {
        try {
            const exif = await exifr.parse(file, {tags: ['DateTimeOriginal', 'DateTime']});
            if (exif) {
                const dateStr = exif.DateTimeOriginal || exif.DateTime;
                if (dateStr) {
                    if (dateStr instanceof Date) {
                        return dateStr.toISOString();
                    }
                    const parts = dateStr.split(/[:\s]/);
                    if (parts.length >= 6) {
                        return `${parts[0]}-${parts[1]}-${parts[2]}T${parts[3]}:${parts[4]}:${parts[5]}`;
                    }
                }
            }
        } catch (e) {
            console.warn('EXIF 解析失败:', e.message);
        }
        return this.getFileDate(file);
    }

    /**
     * 获取文件创建时间
     * @param {File} file - 文件
     * @returns {string} - ISO 日期字符串
     */
    static getFileDate(file) {
        // 尝试从 lastModified 获取
        const date = new Date(file.lastModified);
        if (!isNaN(date.getTime())) {
            return date.toISOString();
        }
        // 回退到当前时间
        return new Date().toISOString();
    }

    /**
     * 判断日期是否合理（年份在 2000 ~ 当前+1 之间）
     * 用于过滤异常时间，如 FILETIME 纪元 1601-01-01
     */
    static _isReasonableDate(isoStr) {
        if (!isoStr) return false;
        const d = new Date(isoStr);
        if (isNaN(d.getTime())) return false;
        const year = d.getUTCFullYear();
        const nowYear = new Date().getUTCFullYear();
        return year >= 2000 && year <= nowYear + 1;
    }

    /**
     * 从 MP4/MOV/M4V 文件中解析 mvhd 的 creation_time
     * 比浏览器 file.lastModified 更可靠，可避免某些 App 转存后时间被污染为 1601 年。
     * @param {File} file - MP4 文件
     * @returns {Promise<string|null>} ISO 日期字符串，解析失败返回 null
     */
    static async getMp4CreationTime(file) {
        try {
            const fileSize = file.size;
            let offset = 0;
            // 逐个读取顶层 box 头部，找到 moov
            while (offset + 8 <= fileSize) {
                const headerBuf = await file.slice(offset, offset + 16).arrayBuffer();
                if (headerBuf.byteLength < 8) break;
                const view = new DataView(headerBuf);
                const bytes = new Uint8Array(headerBuf);

                let size = view.getUint32(0);
                const type = String.fromCharCode(bytes[4], bytes[5], bytes[6], bytes[7]);
                let headerSize = 8;

                if (size === 1) {
                    if (headerBuf.byteLength < 16) break;
                    size = Number(view.getBigUint64(8));
                    headerSize = 16;
                } else if (size === 0) {
                    size = fileSize - offset;
                }
                if (size < 8) break;

                if (type === 'moov') {
                    // 读取 moov 数据部分前 4KB，足够找到 mvhd（mvhd 通常是 moov 第一个子 box）
                    const readSize = Math.min(size, 4096);
                    const moovBuf = await file.slice(offset + headerSize, offset + headerSize + readSize).arrayBuffer();
                    return this._parseMvhdInMoov(moovBuf);
                }

                offset += size;
            }
        } catch (e) {
            console.warn('MP4 mvhd 解析失败:', e.message);
        }
        return null;
    }

    /**
     * 在 moov box 数据中查找 mvhd 并解析 creation_time
     * mvhd 是 moov 的直接子 box，结构：
     *   version(1) + flags(3) + creation_time(4 或 8) + ...
     * creation_time 为 MP4 epoch（1904-01-01 UTC）起的秒数
     */
    static _parseMvhdInMoov(buffer) {
        const view = new DataView(buffer);
        const bytes = new Uint8Array(buffer);
        const len = bytes.length;
        let pos = 0;

        while (pos + 8 <= len) {
            let size = view.getUint32(pos);
            const type = String.fromCharCode(bytes[pos + 4], bytes[pos + 5], bytes[pos + 6], bytes[pos + 7]);
            let headerSize = 8;

            if (size === 1) {
                if (pos + 16 > len) break;
                size = Number(view.getBigUint64(pos + 8));
                headerSize = 16;
            } else if (size === 0) {
                size = len - pos;
            }
            if (size < 8) break;

            if (type === 'mvhd' && pos + headerSize + 4 <= len) {
                const dataPos = pos + headerSize;
                const version = bytes[dataPos];
                let creationTime;
                if (version === 0) {
                    if (dataPos + 8 > len) return null;
                    creationTime = view.getUint32(dataPos + 4);
                } else {
                    if (dataPos + 12 > len) return null;
                    creationTime = Number(view.getBigUint64(dataPos + 4));
                }
                const mp4EpochMs = Date.UTC(1904, 0, 1, 0, 0, 0);
                const date = new Date(mp4EpochMs + creationTime * 1000);
                if (!isNaN(date.getTime())) {
                    return date.toISOString();
                }
                return null;
            }
            pos += size;
        }
        return null;
    }

    /**
     * 获取文件扩展名（小写，含点号）
     */
    static getFileExtension(filename) {
        const idx = filename.lastIndexOf('.');
        return idx >= 0 ? filename.slice(idx).toLowerCase() : '';
    }

    /**
     * 处理单个文件（根据类型分发）
     * @param {File} file - 文件
     * @returns {Promise<{width, height, createTime, thumbnail, thumbnailBlob, originalName}>}
     */
    static async processFile(file) {
        const ext = this.getFileExtension(file.name);
        const imageExts = ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.heic'];
        const videoExts = ['.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.m4v', '.3gp'];

        if (file.type.startsWith('image/') || imageExts.includes(ext)) {
            return await this.processImage(file);
        } else if (file.type.startsWith('video/') || videoExts.includes(ext)) {
            return await this.processVideo(file);
        }
        return {
            width: 0,
            height: 0,
            createTime: this.getFileDate(file),
            thumbnail: null,
            thumbnailBlob: null,
            originalName: file.name
        };
    }

    /**
     * 批量处理文件
     * @param {File[]} files - 文件数组
     * @param {Function} onProgress - 进度回调 (processed, total, currentFile)
     * @param {AbortSignal} signal - 中止信号
     * @returns {Promise<Array>}
     */
    static async batchProcess(files, onProgress, signal) {
        const results = [];
        let processed = 0;
        const total = files.length;
        
        // 分批处理
        for (let i = 0; i < files.length; i += this.BATCH_SIZE) {
            if (signal && signal.aborted) {
                throw new Error('已取消');
            }
            
            const batch = files.slice(i, i + this.BATCH_SIZE);
            const batchPromises = batch.map(file => this.processFile(file));
            
            const batchResults = await Promise.allSettled(batchPromises);
            
            for (let j = 0; j < batchResults.length; j++) {
                processed++;
                const result = batchResults[j];
                
                if (result.status === 'fulfilled') {
                    results.push({
                        ...result.value,
                        originalName: batch[j].name,
                        size: batch[j].size
                    });
                } else {
                    console.error(`处理失败: ${batch[j].name}`, result.reason);
                    results.push({
                        originalName: batch[j].name,
                        size: batch[j].size,
                        error: result.reason?.message || '处理失败'
                    });
                }
                
                if (onProgress) {
                    onProgress(processed, total, batch[j].name);
                }
                
                // 强制垃圾回收（大文件后）
                if (processed % 10 === 0 && window.gc) {
                    window.gc();
                }
            }
            
            // 让出主线程
            await new Promise(resolve => setTimeout(resolve, 10));
        }
        
        return results;
    }

    static async getFileMetadata(file) {
        const ext = this.getFileExtension(file.name);
        const imageExts = ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.heic'];
        const videoExts = ['.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.m4v', '.3gp'];

        if (file.type.startsWith('image/') || imageExts.includes(ext)) {
            return await this.getImageMetadata(file);
        } else if (file.type.startsWith('video/') || videoExts.includes(ext)) {
            return await this.getVideoMetadata(file);
        }
        return {
            width: 0,
            height: 0,
            createTime: this.getFileDate(file),
            originalName: file.name
        };
    }
    
    static async getImageMetadata(file) {
        return new Promise((resolve) => {
            const img = new Image();
            img.onload = () => {
                URL.revokeObjectURL(img.src);
                let createTime = this.getFileDate(file);
                this.getExifDate(file).then(date => {
                    resolve({
                        width: img.naturalWidth,
                        height: img.naturalHeight,
                        createTime: date,
                        originalName: file.name
                    });
                }).catch(() => {
                    resolve({
                        width: img.naturalWidth,
                        height: img.naturalHeight,
                        createTime: createTime,
                        originalName: file.name
                    });
                });
            };
            img.onerror = () => {
                URL.revokeObjectURL(img.src);
                resolve({
                    width: 0,
                    height: 0,
                    createTime: this.getFileDate(file),
                    originalName: file.name
                });
            };
            img.src = URL.createObjectURL(file);
        });
    }
    
    static async getVideoMetadata(file) {
        return new Promise((resolve) => {
            const video = document.createElement('video');
            video.onloadedmetadata = () => {
                URL.revokeObjectURL(video.src);
                resolve({
                    width: video.videoWidth,
                    height: video.videoHeight,
                    createTime: this.getFileDate(file),
                    originalName: file.name
                });
            };
            video.onerror = () => {
                URL.revokeObjectURL(video.src);
                resolve({
                    width: 0,
                    height: 0,
                    createTime: this.getFileDate(file),
                    originalName: file.name
                });
            };
            video.src = URL.createObjectURL(file);
        });
    }

    /**
     * 检查是否有足够内存处理文件
     * @param {number} fileSize - 文件大小（字节）
     * @returns {boolean}
     */
    static checkMemory(fileSize) {
        const memoryMB = fileSize / (1024 * 1024);
        // 允许同时处理的最大文件大小（考虑解码后的内存占用）
        return memoryMB < (window.APP_CONFIG?.media?.singleFileMemoryLimitMB ?? 100); // 单个文件小于 100MB
    }
}

// 导出
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MediaProcessor;
}

# 版本：V1.0
# 作者:fjsay，哔哩哔哩:https://space.bilibili.com/385535315，UID：385535315
# QQ：10789031 （欢迎反馈问题）
# 版本日志
# 这是第一版,代码开源请保留作者信息，谢谢
import ffmpeg
import time
import os
from datetime import datetime, timedelta
import logging
import subprocess
import signal
import threading
import psutil

# 日志配置
LOG_FOLDER = "log"  # 日志保存文件夹
LOG_CONF_FILE = "conf/logconf.txt"  # 日志配置文件（保存日志保留天数）
DEFAULT_LOG_RETENTION_DAYS = 7  # 默认日志保留7天


# 确保日志文件夹存在
def ensure_log_folder():
    if not os.path.exists(LOG_FOLDER):
        os.makedirs(LOG_FOLDER, exist_ok=True)


# 从logconf.txt读取日志保留天数（无文件则默认保留7天）
def get_log_retention_days():
    try:
        if os.path.exists(LOG_CONF_FILE):
            with open(LOG_CONF_FILE, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):  # 跳过注释行
                        days = int(line)
                        return max(days, 1)  # 至少保留1天
        return DEFAULT_LOG_RETENTION_DAYS  # 默认保留7天
    except (ValueError, Exception) as e:
        logging.warning(f"读取日志配置失败，使用默认保留7天: {e}")
        return DEFAULT_LOG_RETENTION_DAYS


# 清理过期日志文件
def clean_expired_logs():
    retention_days = get_log_retention_days()
    current_time = datetime.now()
    deleted_count = 0

    if not os.path.exists(LOG_FOLDER):
        return  # 日志文件夹不存在则无需清理

    for filename in os.listdir(LOG_FOLDER):
        if filename.startswith("log_") and filename.endswith(".txt"):
            file_path = os.path.join(LOG_FOLDER, filename)
            try:
                # 解析文件名中的时间戳（格式：log_20250720_153045.txt）
                time_str = filename[4:-4]  # 提取时间部分
                log_time = datetime.strptime(time_str, "%Y%m%d_%H%M%S")

                # 检查是否超过保留天数
                if (current_time - log_time) > timedelta(days=retention_days):
                    os.remove(file_path)
                    deleted_count += 1
                    logging.info(f"已删除过期日志: {file_path}（超过{retention_days}天）")
            except Exception as e:
                logging.debug(f"跳过格式异常的日志文件 {filename}: {e}")

    if deleted_count > 0:
        logging.info(f"日志清理完成，共删除{deleted_count}个过期文件")


# 配置日志记录（保存到log文件夹，按时间命名）
def setup_logging():
    ensure_log_folder()  # 确保日志文件夹存在

    # 生成当前日志文件名（格式：log_年月日_时分秒.txt）
    current_log_name = f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    current_log_path = os.path.join(LOG_FOLDER, current_log_name)

    # 配置日志格式和处理器
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(message)s',
        handlers=[
            logging.FileHandler(current_log_path, encoding='utf-8'),  # 写入文件
            logging.StreamHandler()  # 同时输出到控制台
        ]
    )

    # 启动时先清理一次过期日志
    clean_expired_logs()


# 定时清理日志（每12小时执行一次）
def schedule_log_cleanup():
    def cleanup_loop():
        while True:
            time.sleep(43200)  # 每12小时执行一次
            clean_expired_logs()

    # 启动后台线程执行清理
    thread = threading.Thread(target=cleanup_loop, daemon=True)
    thread.start()
    logging.info("日志定时清理线程已启动（每12小时执行一次）")


# 配置文件路径
CONFIG_FILE = "conf/conf.txt"

# 输出视频文件保存的根目录
root_output_dir = "Video"
if not os.path.exists(root_output_dir):
    os.makedirs(root_output_dir)

# 确保ffmpeg已安装
try:
    subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
except (subprocess.CalledProcessError, FileNotFoundError):
    logging.error("未找到FFmpeg，请先安装FFmpeg并确保其在系统PATH中")
    exit()


# 安全创建目录的辅助函数
def safe_makedirs(path):
    try:
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        return True
    except Exception as e:
        logging.error(f"创建目录失败: {path}, 错误: {e}")
        # 尝试逐层创建目录
        try:
            parts = os.path.normpath(path).split(os.sep)
            current_path = ""
            for part in parts:
                if part:  # 跳过空部分
                    current_path = os.path.join(current_path, part)
                    if not os.path.exists(current_path):
                        os.makedirs(current_path, exist_ok=True)
            return True
        except Exception as e2:
            logging.error(f"逐层创建目录仍失败: {path}, 错误: {e2}")
            return False


# 从配置文件读取摄像头信息
def read_camera_config(file_path):
    cameras = []
    try:
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):  # 跳过空行和注释
                    parts = line.split(',')
                    # 配置格式：ID, RTSP地址, 保留天数, 录制时长(秒), 保存格式(mp4/flv), 最小文件大小(KB)
                    if len(parts) >= 4:
                        camera_id = parts[0].strip()
                        rtsp_url = parts[1].strip()

                        # 解析保留天数（0表示不删除）
                        try:
                            retention_days = int(parts[2].strip())
                            if retention_days < 0:
                                retention_days = 0
                        except ValueError:
                            logging.warning(f"摄像头 {camera_id} 保留天数无效，使用默认值0")
                            retention_days = 0

                        # 解析录制时长（秒）
                        try:
                            record_duration = int(parts[3].strip())
                            if record_duration <= 0:
                                record_duration = 60
                        except ValueError:
                            logging.warning(f"摄像头 {camera_id} 录制时长无效，使用默认值60秒")
                            record_duration = 60

                        # 解析保存格式
                        save_format = 'flv'
                        if len(parts) > 4:
                            fmt = parts[4].strip().lower()
                            if fmt in ['mp4', 'flv']:
                                save_format = fmt
                            else:
                                logging.warning(f"摄像头 {camera_id} 格式无效，使用默认flv")

                        # 解析最小文件大小（KB）
                        min_file_size_kb = 0
                        if len(parts) > 5:
                            try:
                                min_file_size_kb = int(parts[5].strip())
                                if min_file_size_kb < 0:
                                    min_file_size_kb = 0
                            except ValueError:
                                logging.warning(f"摄像头 {camera_id} 最小文件大小无效，使用默认值0")
                                min_file_size_kb = 0

                        cameras.append({
                            'id': camera_id,
                            'url': rtsp_url,
                            'retention_days': retention_days,
                            'record_duration': record_duration,
                            'save_format': save_format,
                            'min_file_size_kb': min_file_size_kb
                        })
                        logging.info(
                            f"已加载摄像头配置: {camera_id} - {rtsp_url} "
                            f"(保留{retention_days}天，每次录制{record_duration}秒，格式{save_format}，"
                            f"最小文件大小{min_file_size_kb}KB)"
                        )
                    else:
                        logging.warning(f"配置行格式不正确（至少需要4个字段）: {line}")
    except Exception as e:
        logging.error(f"读取配置文件失败: {e}")
    return cameras


# 生成带时间路径的视频文件名
def get_video_file_path(camera_id, save_format):
    now = datetime.now()
    dir_path = os.path.join(
        root_output_dir,
        camera_id,
        f"{now.year}年",
        f"{now.month}月",
        f"{now.day}日",
        f"{now.hour}时"
    )

    if not safe_makedirs(dir_path):
        alt_dir = os.path.join(root_output_dir, "unknown_path")
        safe_makedirs(alt_dir)
        return os.path.join(alt_dir, f"{camera_id}_{now.strftime('%Y%m%d_%H%M%S')}.{save_format}")

    file_name = f"{camera_id}_{now.strftime('%Y%m%d_%H%M%S')}.{save_format}"
    return os.path.join(dir_path, file_name)


# 从完整文件路径解析时间信息
def parse_file_info(file_path):
    try:
        file_name = os.path.basename(file_path)
        dir_name = os.path.dirname(file_path)

        # 解析文件名中的时间戳和格式
        parts = file_name.split('_')
        if len(parts) < 3:
            return None

        # 提取文件格式
        file_ext = parts[-1].split('.')
        if len(file_ext) != 2:
            return None
        file_format = file_ext[1].lower()

        # 解析目录中的时间信息
        dir_parts = dir_name.split(os.sep)
        if len(dir_parts) < 6:  # 至少需要包含根目录/摄像头ID/年/月/日/时
            return None

        # 提取各时间部分（处理带中文的目录名）
        camera_id = dir_parts[-5]  # 摄像头ID在路径的第5层
        year = int(dir_parts[-4].replace('年', ''))
        month = int(dir_parts[-3].replace('月', ''))
        day = int(dir_parts[-2].replace('日', ''))
        hour = int(dir_parts[-1].replace('时', ''))

        # 提取文件名中的时分秒
        time_part = file_ext[0]
        try:
            minute = int(time_part[0:2])
            second = int(time_part[2:4])
        except:
            # 如果时分秒解析失败，使用目录中的小时信息和默认值
            minute = 0
            second = 0

        # 构建完整的时间戳
        timestamp = datetime(year, month, day, hour, minute, second)

        return {
            'camera_id': camera_id,
            'timestamp': timestamp,
            'file_path': file_path,
            'format': file_format
        }
    except Exception as e:
        logging.debug(f"解析文件路径失败 {file_path}: {e}")
        return None


# 清理过期录像文件
def clean_expired_recordings(camera_id, retention_days):
    # 保留天数为0时不清理
    if retention_days <= 0:
        return 0, 0.0, 0

    try:
        current_time = datetime.now()
        expired_count = 0
        freed_size = 0.0  # MB
        deleted_dirs = 0

        # 构建摄像头的根目录路径
        camera_root_dir = os.path.join(root_output_dir, camera_id)
        if not os.path.exists(camera_root_dir):
            return 0, 0.0, 0

        # 递归遍历目录查找所有视频文件（支持mp4和flv）
        for root, _, files in os.walk(camera_root_dir):
            for filename in files:
                if filename.endswith(('.mp4', '.flv')):
                    file_path = os.path.join(root, filename)
                    file_info = parse_file_info(file_path)
                    if file_info and file_info['camera_id'] == camera_id:
                        # 计算文件年龄（天）
                        file_age_days = (current_time - file_info['timestamp']).total_seconds() / (3600 * 24)
                        if file_age_days > retention_days:
                            # 删除过期文件
                            try:
                                file_size = os.path.getsize(file_path)
                                os.remove(file_path)
                                expired_count += 1
                                freed_size += file_size / (1024 * 1024)  # 转换为MB
                                logging.info(f"已删除过期文件: {file_path} ({file_size / 1024 / 1024:.2f} MB)")
                            except Exception as e:
                                logging.error(f"删除文件 {file_path} 失败: {e}")

        # 清理空目录（从最深层开始）
        deleted_dirs = cleanup_empty_directories(camera_root_dir)

        return expired_count, freed_size, deleted_dirs
    except Exception as e:
        logging.error(f"清理摄像头 {camera_id} 过期文件时出错: {e}")
        return 0, 0.0, 0


# 递归清理空目录
def cleanup_empty_directories(root_dir):
    deleted_count = 0

    # 先递归处理子目录
    if os.path.isdir(root_dir):
        for item in os.listdir(root_dir):
            item_path = os.path.join(root_dir, item)
            if os.path.isdir(item_path):
                deleted_count += cleanup_empty_directories(item_path)

    # 检查当前目录是否为空
    if os.path.isdir(root_dir) and not os.listdir(root_dir):
        try:
            # 跳过根目录，不删除
            if root_dir != os.path.join(root_output_dir) and root_dir != root_output_dir:
                os.rmdir(root_dir)
                deleted_count += 1
                logging.info(f"已删除空目录: {root_dir}")
        except Exception as e:
            logging.error(f"删除空目录 {root_dir} 失败: {e}")

    return deleted_count


# 检查并删除过小的文件
def check_and_delete_small_file(file_path, min_file_size_kb):
    """
    检查文件是否小于指定大小，若是则删除
    :param file_path: 文件路径
    :param min_file_size_kb: 最小文件大小（KB），0表示不检查
    :return: 是否删除
    """
    if min_file_size_kb <= 0 or not os.path.exists(file_path):
        return False

    try:
        # 转换为字节（1KB = 1024字节）
        min_size_bytes = min_file_size_kb * 1024
        file_size = os.path.getsize(file_path)

        if file_size < min_size_bytes:
            os.remove(file_path)
            logging.info(
                f"已删除过小文件: {file_path} "
                f"({file_size / 1024:.2f}KB < {min_file_size_kb}KB)"
            )
            return True
        return False
    except Exception as e:
        logging.error(f"检查/删除过小文件失败 {file_path}: {e}")
        return False


# 录制视频
def record_video(camera_info):
    camera_id = camera_info['id']
    rtsp_url = camera_info['url']
    retention_days = camera_info['retention_days']
    record_duration = camera_info['record_duration']
    save_format = camera_info['save_format']
    min_file_size_kb = camera_info['min_file_size_kb']  # 最小文件大小（KB）

    # 每小时执行一次过期文件清理（如果需要）
    cleanup_interval = 3600
    last_cleanup = time.time()

    while True:
        # 获取带路径的文件名
        output_file = get_video_file_path(camera_id, save_format)

        logging.info(
            f"开始录制摄像头 {camera_id}，保存路径：{output_file} "
            f"(本次录制{record_duration}秒，格式{save_format})"
        )

        try:
            # 构建ffmpeg命令
            stream = ffmpeg.input(rtsp_url)
            video_stream = stream.video
            audio_stream = stream.audio

            # 设置输出参数
            if save_format == 'mp4':
                output = ffmpeg.output(
                    video_stream, audio_stream,
                    output_file,
                    codec='copy',
                    t=record_duration
                )
            else:  # FLV格式
                output = ffmpeg.output(
                    video_stream, audio_stream,
                    output_file,
                    codec='copy',
                    t=record_duration,
                    f='flv'
                )

            # 运行ffmpeg命令
            process = ffmpeg.run_async(output, overwrite_output=True)
            process.wait()

            if process.returncode == 0:
                logging.info(f"摄像头 {camera_id} 视频保存成功：{output_file}")

                # 录制完成后立即检查并删除过小文件
                if min_file_size_kb > 0:
                    check_and_delete_small_file(output_file, min_file_size_kb)
            else:
                logging.error(f"摄像头 {camera_id} 录制失败，ffmpeg返回代码：{process.returncode}")
                # 录制失败时也检查是否生成了过小文件并删除
                if os.path.exists(output_file) and min_file_size_kb > 0:
                    check_and_delete_small_file(output_file, min_file_size_kb)

        except Exception as e:
            logging.error(f"摄像头 {camera_id} 录制过程中发生错误: {e}")
            # 发生异常时检查是否生成了过小文件并删除
            if os.path.exists(output_file) and min_file_size_kb > 0:
                check_and_delete_small_file(output_file, min_file_size_kb)
            time.sleep(5)  # 错误发生后等待5秒再重试

        # 检查是否需要清理过期文件
        current_time = time.time()
        if retention_days > 0 and (current_time - last_cleanup >= cleanup_interval):
            deleted_files, freed_size, deleted_dirs = clean_expired_recordings(camera_id, retention_days)
            if deleted_files > 0 or deleted_dirs > 0:
                logging.info(
                    f"摄像头 {camera_id} 清理完成: "
                    f"删除 {deleted_files} 个过期文件，释放 {freed_size:.2f} MB 空间，"
                    f"删除 {deleted_dirs} 个空目录"
                )
            last_cleanup = current_time


# 主程序
if __name__ == "__main__":
    # 初始化日志配置
    setup_logging()
    # 启动日志定时清理线程
    schedule_log_cleanup()

    # 读取摄像头配置
    cameras = read_camera_config(CONFIG_FILE)

    if not cameras:
        logging.error("没有找到有效的摄像头配置，程序退出")
        exit()

    # 为每个摄像头创建录制线程
    recording_threads = []
    for camera in cameras:
        thread = threading.Thread(target=record_video, args=(camera,))
        thread.daemon = True
        thread.start()
        recording_threads.append(thread)
        logging.info(f"已启动摄像头 {camera['id']} 的录制线程")

    try:
        # 保持主线程运行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("监控录像机已停止")
    finally:
        # 确保所有ffmpeg进程都被终止
        for proc in psutil.process_iter():
            if 'ffmpeg' in proc.name().lower():
                try:
                    proc.send_signal(signal.SIGTERM)
                    logging.info(f"终止ffmpeg进程: {proc.pid}")
                except Exception as e:
                    logging.error(f"终止ffmpeg进程失败: {e}")

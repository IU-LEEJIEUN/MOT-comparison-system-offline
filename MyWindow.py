import os
import shutil
import sys
from PyQt5 import uic, QtGui, QtCore, QtWidgets
from PyQt5.QtCore import QDateTime, QTimer, QTime, Qt
from PyQt5.QtGui import QIcon, QPixmap, QImage, QFont
from PyQt5.QtWidgets import QApplication, QWidget, QFileDialog, QMessageBox, QProgressDialog, QTableWidgetItem
import subprocess
from PyQt5.QtCore import QThread
import torch

from Move2Center import center
from CircularQueue import CircularQueue
import cv2
import resources_rc


def convert_to_pixmap(frame):
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = QImage(frame, frame.shape[1], frame.shape[0], QImage.Format_RGB888)
    pixmap = QPixmap.fromImage(image)
    return pixmap


def read_summary_file(file_path):
    with open(file_path, 'r') as f:
        lines = f.readlines()
        keys = lines[0].split()
        values = lines[1].split()
        return dict(zip(keys, values))


def get_summary_dict(path, prefix):
    result = {}
    for root, dirs, files in os.walk(path):
        for d in dirs:
            if d.startswith(prefix):
                dir_path = os.path.join(root, d)
                d = d.split('_')[0]
                for file in os.listdir(dir_path):
                    if file.endswith('summary.txt'):
                        file_path = os.path.join(dir_path, file)
                        result[d] = read_summary_file(file_path)
    return result


class MyProgressDialog(QProgressDialog):
    def __init__(self, *args, **kwargs):
        super(MyProgressDialog, self).__init__(*args, **kwargs)
        self.completed = False

    def setCompleted(self):
        self.completed = True

    def closeEvent(self, event):
        if not self.completed:
            reply = QMessageBox.question(self, 'Message', "Are you sure to quit?", QMessageBox.Yes | QMessageBox.No,
                                         QMessageBox.No)
            if reply == QMessageBox.Yes:
                event.accept()
                if os.path.exists('./test_video/sequences'):
                    shutil.rmtree('./test_video/sequences')
                else:
                    return
            else:
                event.ignore()


class Tracking_Thread(QThread):

    def __init__(self, cmd):
        super().__init__()
        self.cmd = cmd

    def run(self):
        subprocess.call(self.cmd)


class MyWindow(QWidget):

    def __init__(self):
        super().__init__()
        self.video_caps = None
        self.ui = None
        self.init_ui()
        self.worker1 = None
        self.worker2 = None
        self.worker3 = None
        self.tracked_video1 = None
        self.tracked_video2 = None
        self.tracked_video3 = None
        self.algo_list = []
        self.video_cap = cv2.VideoCapture()
        self.total_frames = 0  # total frames
        self.mFrameRate = 0  # frame rate
        self.mIsBroadcast = False  # broadcast flag
        self.mCurrentFrame = 0  # current frame
        self.mFrame = None  # picture frame information
        self.input_frame = 0  # the frame you want to skip
        self.msg_box = QMessageBox()  # various Message Box
        self.ALGOName_queue = CircularQueue(3)
        self.msg_box.setWindowIcon(QIcon("./pic/logo.png"))
        self.ui.SkipBtn.setShortcut(QtCore.Qt.Key_Return)  # Set the shortcut key to trigger skip
        self.ui.FrameEdit.setValidator(QtGui.QIntValidator())  # Only numbers can be inputted in the FrameEdit
        self.mCurrentTime = QDateTime.fromString("00:00:00", "hh:mm:ss")
        self.ui.timeLabel.setText(self.mCurrentTime.toString("hh:mm:ss"))
        self.ui.FrameEdit.setPlaceholderText("number")
        self.ui.actionOpen.triggered.connect(self.process_video)
        self.ui.actionSORT.triggered.connect(self.Select_SORT)
        self.ui.actionDeepSORT.triggered.connect(self.Select_DeepSORT)
        self.ui.actionByteTrack.triggered.connect(self.Select_ByteTrack)
        self.ui.actionClear.triggered.connect(self.Clear)
        self.ui.horizontalSlider.sliderMoved.connect(self.sliderMoved)
        self.ui.broadcastBtn.clicked.connect(self.broadcast)
        self.ui.stopBtn.clicked.connect(self.stop)
        self.ui.SkipBtn.clicked.connect(self.skip)
        self.ui.PreFrameBtn.clicked.connect(self.pre_frame)
        self.ui.NextFrameBtn.clicked.connect(self.next_frame)
        self.theTimer = QTimer(self)
        self.theTimer.timeout.connect(self.updateImage)
        self.ui.broadcastBtn.setEnabled(False)  # The broadcastBtn cannot be used before opening the video
        self.set_table_style()
        self.setStop_BtnStyle()
        self.setCentral_widgetStyle()
        self.setStatus_barStyle()

    def init_ui(self):
        self.ui = uic.loadUi("./MainWindow.ui")
        self.ui.setWindowIcon(QIcon("./pic/logo.png"))
        self.setBroadcastState_BtnStyle()
        self.setPauseState_BtnStyle()

        #     删除'./test_video'目录下的sequences文件夹
        #     shutil.rmtree('./test_video/sequences')
        #     # 删除'./test_video'目录下以指定开头的文件夹
        #     prefixes = [self.ui.ALGOname1.text(), self.ui.ALGOname2.text(), self.ui.ALGOname3.text()]
        #     for prefix in prefixes:
        #         for dir_name in os.listdir('./test_video'):
        #             if dir_name.startswith(prefix):
        #                 shutil.rmtree(os.path.join('./test_video', dir_name))
        #
        #     # 删除'./tracker'目录下的results文件夹
        #     shutil.rmtree('./tracker/results')

    def process_video(self):
        if not self.ui.ALGOname1.text() or not self.ui.ALGOname2.text() or not self.ui.ALGOname3.text():
            self.msg_box.setIcon(QMessageBox.Warning)
            self.msg_box.setText("Please select three algorithms first")
            self.msg_box.setWindowTitle("Information")
            self.msg_box.exec_()
        else:
            video_path, _ = QFileDialog.getOpenFileName(self, "Open Video File", "",
                                                        "Videos (*.mp4 *.avi *.mkv);;All Files (*)")
            # if os.path.exists('./test_video/sequences'):
            #     shutil.rmtree('./test_video/sequences')
            # if os.path.exists('./tracker/results'):
            #     shutil.rmtree('./tracker/results')
            # prefixes = [self.ui.ALGOname1.text(), self.ui.ALGOname2.text(), self.ui.ALGOname3.text()]
            # for prefix in prefixes:
            #     for dir_name in os.listdir('./test_video'):
            #             if dir_name.startswith(prefix):
            #                 shutil.rmtree(os.path.join('./test_video', dir_name))
            if video_path:
                filename = os.path.basename(video_path)
                filename, ext = os.path.splitext(filename)
                assert os.path.exists(video_path), 'the video does not exist! '
                if self.convert_video_to_frame(video_path, filename):
                    self.msg_box.setText("Image sequence was converted successfully")
                    self.msg_box.setWindowTitle("Success")
                    self.msg_box.exec_()
                    track1 = self.ui.ALGOname1.text()
                    track2 = self.ui.ALGOname2.text()
                    track3 = self.ui.ALGOname3.text()
                    subprocess_path = './tracker/track.py'
                    cmd1 = ['python', subprocess_path, str('--save_videos'), str('--tracker'), track1]
                    cmd2 = ['python', subprocess_path, str('--save_videos'), str('--tracker'), track2]
                    cmd3 = ['python', subprocess_path, str('--save_videos'), str('--tracker'), track3]
                    self.worker1 = Tracking_Thread(cmd1)
                    self.worker2 = Tracking_Thread(cmd2)
                    self.worker3 = Tracking_Thread(cmd3)
                    self.worker1.finished.connect(self.start_worker2)
                    self.worker2.finished.connect(self.start_worker3)
                    self.worker3.finished.connect(self.tracked_completed)
                    self.worker1.start()
                else:
                    pass
            else:
                pass

    def tracked_completed(self):
        folder_paths = []
        base_folder = "./test_video"  # 指定目录路径
        for folder_name in os.listdir(base_folder):
            if folder_name.startswith(("SORT", "DeepSORT", "ByteTrack")) and os.path.isdir(
                    os.path.join(base_folder, folder_name)):
                folder_path = os.path.join(base_folder, folder_name)
                folder_paths.append(folder_path)
        video_paths = []
        for folder_path in folder_paths:
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    if file.endswith('.mp4'):
                        video_path = os.path.join(root, file)
                        video_paths.append(video_path)
        for path in video_paths:
            folder_name = os.path.basename(os.path.dirname(path))
            algorithm_name = folder_name.split('_')[0]
            if algorithm_name == self.ui.ALGOname1.text():
                self.tracked_video1 = path
            elif algorithm_name == self.ui.ALGOname2.text():
                self.tracked_video2 = path
            elif algorithm_name == self.ui.ALGOname3.text():
                self.tracked_video3 = path
        self.ui.broadcastBtn.setEnabled(True)
        self.updateImage()
        path = './tracker/results'
        prefixes = [self.ui.ALGOname1.text(), self.ui.ALGOname2.text(), self.ui.ALGOname3.text()]
        # dicts = []
        # for prefix in prefixes:
        #     dicts.append(get_summary_dict(path, prefix))
        dicts = {}
        for prefix in prefixes:
            dicts[prefix] = get_summary_dict(path, prefix)
        self.read_indicator(dicts)

    def updateImage(self):
        if self.mCurrentFrame >= self.total_frames:
            self.mCurrentFrame = 0
            self.ui.horizontalSlider.setValue(self.mCurrentFrame)
            self.mCurrentTime = QDateTime.fromString("00:00:00", "hh:mm:ss")
            self.ui.timeLabel.setText(self.mCurrentTime.toString("hh:mm:ss"))
            self.theTimer.stop()
            self.ui.VideoWindow1.clear()
            self.ui.VideoWindow2.clear()
            self.ui.VideoWindow3.clear()
            return
        for video_window, video_path in zip([self.ui.VideoWindow1, self.ui.VideoWindow2, self.ui.VideoWindow3],
                                            [self.tracked_video1, self.tracked_video2, self.tracked_video3]):
            self.video_cap = cv2.VideoCapture(video_path)
            self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, self.mCurrentFrame)
            success, self.mFrame = self.video_cap.read()
            if success:
                pixmap = convert_to_pixmap(self.mFrame)
                video_window.setPixmap(pixmap)
                video_window.setScaledContents(True)
                self.ui.CurrentFrame.setText("Current Frame:{}".format(int(self.mCurrentFrame)))
        self.ui.horizontalSlider.setValue(int(self.mCurrentFrame))
        self.mCurrentFrame += 1
        self.ui.horizontalSlider.setMaximum(self.total_frames)
        self.mFrameRate = self.video_cap.get(cv2.CAP_PROP_FPS)
        self.mCurrentTime = QDateTime.fromString("00:00:00", "hh:mm:ss").addMSecs(
            int(1000 * self.mCurrentFrame / self.mFrameRate))
        self.ui.timeLabel.setText(self.mCurrentTime.toString("hh:mm:ss"))
        self.ui.FPS.setText("FPS:{}".format(int(self.mFrameRate)))

    # Slot function of slide moved
    def sliderMoved(self, position):
        if self.ui.VideoWindow1.pixmap() is not None:
            # Update current frame and time for each video window
            for video_window, video_path in zip([self.ui.VideoWindow1, self.ui.VideoWindow2, self.ui.VideoWindow3],
                                                [self.tracked_video1, self.tracked_video2, self.tracked_video3]):
                video_cap = cv2.VideoCapture(video_path)
                video_cap.set(cv2.CAP_PROP_POS_FRAMES, position)
                self.mCurrentFrame = position
                self.mCurrentTime = QDateTime.fromString("00:00:00", "hh:mm:ss").addMSecs(
                    int(1000 * position / self.mFrameRate))
                ret, mFrame = video_cap.read()
                if ret:
                    pixmap = convert_to_pixmap(mFrame)
                    video_window.setPixmap(pixmap)
                    video_window.setScaledContents(True)
                video_cap.release()
            self.ui.timeLabel.setText(self.mCurrentTime.toString("hh:mm:ss"))
            self.ui.CurrentFrame.setText("Current Frame:{}".format(int(self.mCurrentFrame)))
            self.ui.FPS.setText("FPS:{}".format(int(self.mFrameRate)))
        else:
            self.ui.horizontalSlider.setValue(0)
            self.msg_box.setIcon(QMessageBox.Warning)
            self.msg_box.setText("Please open the video file first")
            self.msg_box.setWindowTitle("Warning")
            self.msg_box.show()

    def broadcast(self):
        if not self.mIsBroadcast:
            self.setPauseState_BtnStyle()
            self.mIsBroadcast = True
            self.theTimer.start(int(1000 / self.mFrameRate))
            self.ui.FPS.setText("FPS:{}".format(int(self.mFrameRate)))
        else:
            self.setBroadcastState_BtnStyle()
            self.mIsBroadcast = False
            self.theTimer.stop()

    def stop(self):
        self.setBroadcastState_BtnStyle()
        self.mIsBroadcast = False
        self.mCurrentFrame = 0
        self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self.ui.horizontalSlider.setValue(self.mCurrentFrame)
        self.mCurrentTime = QDateTime.fromString("00:00:00", "hh:mm:ss")
        self.ui.timeLabel.setText(self.mCurrentTime.toString("hh:mm:ss"))
        self.ui.FPS.setText("FPS:")
        self.ui.CurrentFrame.setText("Current Frame:")
        self.ui.VideoWindow1.clear()
        self.ui.VideoWindow2.clear()
        self.ui.VideoWindow3.clear()
        self.theTimer.stop()

    def skip(self):
        if self.ui.FrameEdit.text() == '':
            self.msg_box.setIcon(QMessageBox.Question)
            self.msg_box.setText("Please input a number")
            self.msg_box.setWindowTitle("Warning")
            self.msg_box.exec_()
        else:
            self.input_frame = int(self.ui.FrameEdit.text())
        if self.input_frame < 0 and self.ui.VideoWindow1.pixmap() is not None:
            self.msg_box.setIcon(QMessageBox.Warning)
            self.msg_box.setText("Please input the correct number of frames")
            self.msg_box.setWindowTitle("Warning")
            self.msg_box.exec_()
        elif self.input_frame > self.total_frames and self.ui.VideoWindow1.pixmap() is not None:
            self.msg_box.setIcon(QMessageBox.Warning)
            self.msg_box.setText("The number you inputted is greater than the total frames of the video."
                                 "Please input the correct number of frames")
            self.msg_box.setWindowTitle("Warning")
            self.msg_box.exec_()
        if self.ui.VideoWindow1.pixmap() is None:
            self.msg_box.setIcon(QMessageBox.Warning)
            self.msg_box.setText("Please open the video file first")
            self.msg_box.setWindowTitle("Warning")
            self.msg_box.exec_()
        elif 0 <= self.input_frame <= self.total_frames:
            self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, self.input_frame)
            self.mCurrentFrame = self.input_frame
            self.mCurrentTime = QDateTime.fromString("00:00:00", "hh:mm:ss").addMSecs(
                int(1000 * self.input_frame / self.mFrameRate))
            self.ui.timeLabel.setText(self.mCurrentTime.toString("hh:mm:ss"))
            self.ui.horizontalSlider.setValue(self.mCurrentFrame)
            for video_window, video_path in zip([self.ui.VideoWindow1, self.ui.VideoWindow2, self.ui.VideoWindow3],
                                                [self.tracked_video1, self.tracked_video2, self.tracked_video3]):
                video_cap = cv2.VideoCapture(video_path)
                video_cap.set(cv2.CAP_PROP_POS_FRAMES, self.mCurrentFrame)
                success, self.mFrame = video_cap.read()
                if success:
                    pixmap = convert_to_pixmap(self.mFrame)
                    video_window.setPixmap(pixmap)
                    video_window.setScaledContents(True)
            self.ui.horizontalSlider.setValue(int(self.mCurrentFrame))
            current_msec = int((self.mCurrentFrame / self.mFrameRate) * 1000)
            current_time = QTime(0, 0, 0, 0).addMSecs(current_msec)
            self.ui.timeLabel.setText(current_time.toString("hh:mm:ss"))
            self.ui.CurrentFrame.setText("Current Frame:{}".format(int(self.mCurrentFrame)))

    def pre_frame(self):
        self.theTimer.stop()
        self.setBroadcastState_BtnStyle()
        if self.ui.VideoWindow1.pixmap() is None:
            pass
        if self.mCurrentFrame < 0:
            self.mCurrentFrame = 0
        self.mCurrentFrame -= 1
        for video_window, video_path in zip([self.ui.VideoWindow1, self.ui.VideoWindow2, self.ui.VideoWindow3],
                                            [self.tracked_video1, self.tracked_video2, self.tracked_video3]):
            video_cap = cv2.VideoCapture(video_path)
            video_cap.set(cv2.CAP_PROP_POS_FRAMES, self.mCurrentFrame)
            success, self.mFrame = video_cap.read()
            if success:
                pixmap = convert_to_pixmap(self.mFrame)
                video_window.setPixmap(pixmap)
                video_window.setScaledContents(True)
        self.ui.horizontalSlider.setValue(int(self.mCurrentFrame))
        current_msec = int((self.mCurrentFrame / self.mFrameRate) * 1000)
        current_time = QTime(0, 0, 0, 0).addMSecs(current_msec)
        self.ui.timeLabel.setText(current_time.toString("hh:mm:ss"))
        self.ui.CurrentFrame.setText("Current Frame:{}".format(int(self.mCurrentFrame)))

    def next_frame(self):
        self.theTimer.stop()
        self.setBroadcastState_BtnStyle()
        if self.ui.VideoWindow1.pixmap() is None:
            pass
        if self.mCurrentFrame > self.total_frames:
            self.mCurrentFrame = 0
        self.mCurrentFrame += 1
        for video_window, video_path in zip([self.ui.VideoWindow1, self.ui.VideoWindow2, self.ui.VideoWindow3],
                                            [self.tracked_video1, self.tracked_video2, self.tracked_video3]):
            video_cap = cv2.VideoCapture(video_path)
            video_cap.set(cv2.CAP_PROP_POS_FRAMES, self.mCurrentFrame)
            success, self.mFrame = video_cap.read()
            if success:
                pixmap = convert_to_pixmap(self.mFrame)
                video_window.setPixmap(pixmap)
                video_window.setScaledContents(True)
        self.ui.horizontalSlider.setValue(int(self.mCurrentFrame))
        current_msec = int((self.mCurrentFrame / self.mFrameRate) * 1000)
        current_time = QTime(0, 0, 0, 0).addMSecs(current_msec)
        self.ui.timeLabel.setText(current_time.toString("hh:mm:ss"))
        self.ui.CurrentFrame.setText("Current Frame:{}".format(int(self.mCurrentFrame)))

    def Select_SORT(self):
        self.ALGOName_queue.enqueue("SORT")
        self.ui.ALGOname1.setText(self.ALGOName_queue.data[0])
        self.ui.ALGOname2.setText(self.ALGOName_queue.data[1])
        self.ui.ALGOname3.setText(self.ALGOName_queue.data[2])
        self.algo_list = self.ALGOName_queue.data
        self.ui.indicator_table.setVerticalHeaderLabels(self.algo_list)

    def Select_DeepSORT(self):
        self.ALGOName_queue.enqueue("DeepSORT")
        self.ui.ALGOname1.setText(self.ALGOName_queue.data[0])
        self.ui.ALGOname2.setText(self.ALGOName_queue.data[1])
        self.ui.ALGOname3.setText(self.ALGOName_queue.data[2])
        self.algo_list = self.ALGOName_queue.data
        self.ui.indicator_table.setVerticalHeaderLabels(self.algo_list)

    def Select_ByteTrack(self):
        self.ALGOName_queue.enqueue("ByteTrack")
        self.ui.ALGOname1.setText(self.ALGOName_queue.data[0])
        self.ui.ALGOname2.setText(self.ALGOName_queue.data[1])
        self.ui.ALGOname3.setText(self.ALGOName_queue.data[2])
        self.algo_list = self.ALGOName_queue.data
        self.ui.indicator_table.setVerticalHeaderLabels(self.algo_list)

    def Clear(self):
        self.ALGOName_queue.data = [None] * 3
        self.ALGOName_queue.head = 0
        self.ALGOName_queue.tail = 0
        self.ui.ALGOname1.setText(self.ALGOName_queue.data[0])
        self.ui.ALGOname2.setText(self.ALGOName_queue.data[1])
        self.ui.ALGOname3.setText(self.ALGOName_queue.data[2])
        self.algo_list = ['1', '2', '3']
        self.ui.indicator_table.setVerticalHeaderLabels(self.algo_list)

    def convert_video_to_frame(self, video_path, filename):
        # Create a directory to store the extracted frames
        save_path = os.path.join('./test_video', 'sequences', filename)
        if not os.path.exists(save_path):
            os.makedirs(save_path)
        # initialize progress dialog
        progress_dialog = MyProgressDialog("Converting video to image sequence...", None, 0, 100, self)
        progress_dialog.setWindowTitle("Converting")
        progress_dialog.setWindowIcon(QIcon("./pic/logo.png"))
        progress_dialog.setModal(True)
        progress_dialog.setWindowModality(Qt.WindowModal)
        progress_dialog.show()
        # Read the video and extract frames
        cap = cv2.VideoCapture(video_path)
        # get video properties
        self.total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_id = 0
        # read and save frames
        while True:
            # read a frame
            ret, frame = cap.read()
            # break if no frame is read
            if not ret:
                break
            # save frame as an image
            image_path = os.path.join(save_path, f'frame_{frame_id:06d}.jpg')
            cv2.imwrite(image_path, frame)
            # update progress dialog
            progress = int((frame_id / self.total_frames) * 100)
            progress_dialog.setValue(progress)
            # check if cancel button is pressed
            if progress_dialog.wasCanceled():
                break
            # increment frame count
            frame_id += 1
        # release video file
        cap.release()
        # close progress dialog
        progress_dialog.setCompleted()
        progress_dialog.close()
        if os.path.exists('./test_video/sequences'):
            return True
        else:
            pass

    def check_select_algo(self):
        if not self.ui.ALGOname1.text() or not self.ui.ALGOname2.text() or not self.ui.ALGOname3.text():
            self.msg_box.setIcon(QMessageBox.Warning)
            self.msg_box.setText("Please select three algorithms first")
            self.msg_box.setWindowTitle("Warning")
            self.msg_box.exec_()

    def set_table_style(self):
        self.ui.indicator_table.setRowCount(3)
        self.ui.indicator_table.setColumnCount(15)
        indicator_list = ['HOTA', 'DetA', 'AssA', 'DetRe', 'DetPr', 'AssRe',
                          'MOTA', 'MOTP', 'IDSW', 'MT', 'ML', 'Frag', 'IDF1',
                          'IDR', 'IDP']
        self.ui.indicator_table.setHorizontalHeaderLabels(indicator_list)
        self.ui.indicator_table.setStyleSheet("QTableWidget QTableCornerButton::section,QTableWidget "
                                              "QHeaderView::section, QTableWidget::item { border: 1px solid black; }")
        self.ui.indicator_table.horizontalHeader().setStretchLastSection(True)  # 单元横向高度自适应。铺满窗口
        self.ui.indicator_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.ui.indicator_table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.ui.indicator_table.verticalHeader().setStretchLastSection(True)  # 单元竖直高度自适应。铺满窗口
        self.ui.indicator_table.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.ui.indicator_table.verticalHeader().setDefaultAlignment(Qt.AlignCenter)
        font = self.ui.indicator_table.font()
        font.setBold(True)
        font.setPointSize(12)
        self.ui.indicator_table.horizontalHeader().setFont(font)
        self.ui.indicator_table.verticalHeader().setFont(font)
        self.ui.indicator_table.setFont(QFont("song", 12))

    def read_indicator(self, data_dict):
        for row in range(self.ui.indicator_table.rowCount()):
            row_header = self.ui.indicator_table.verticalHeaderItem(row).text()
            row_data = data_dict[row_header][row_header]
            for col in range(self.ui.indicator_table.columnCount()):
                col_header = self.ui.indicator_table.horizontalHeaderItem(col).text()
                item = QTableWidgetItem(str(row_data[col_header]))
                item.setTextAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)
                self.ui.indicator_table.setItem(row, col, item)


    def start_worker2(self):
        self.worker2.start()

    def start_worker3(self):
        self.worker3.start()

    def setBroadcastState_BtnStyle(self):
        style = "QPushButton { \
            border: 0px; \
            image: url(:/broadcastBtn_normal.png); \
        } \
        QPushButton:hover { \
            image: url(:/broadcastBtn_hover.png); \
        } \
        QPushButton:pressed { \
            image: url(:/broadcastBtn_press.png); \
        }"
        self.ui.broadcastBtn.setStyleSheet(style)

    def setPauseState_BtnStyle(self):
        style = "QPushButton { \
            border: 0px; \
            image: url(:/pauseBtn_normal.png); \
        } \
        QPushButton:hover { \
            image: url(:/pauseBtn_hover.png); \
        } \
        QPushButton:pressed { \
            image: url(:/pauseBtn_press.png); \
        }"
        self.ui.broadcastBtn.setStyleSheet(style)

    def setStop_BtnStyle(self):
        style = "QPushButton { \
            border:0px;\
            image: url(:/stopBtn_normal.png);\
        }\
        QPushButton:hover {\
            image: url(:/stopBtn_normal.png);\
        }\
        QPushButton:pressed {\
            image: url(:/stopBtn_press.png);\
        }"
        self.ui.stopBtn.setStyleSheet(style)

    def setCentral_widgetStyle(self):
        style = "#centralwidget{ \
            border-image: url(:/background_1.png);\
            }"
        self.ui.centralwidget.setStyleSheet(style)

    def setStatus_barStyle(self):
        style = "#statusbar{ \
            border-image: url(:/background.png);\
            }"
        self.ui.statusbar.setStyleSheet(style)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = MyWindow()
    w.ui.setWindowTitle("Multi-target detection and tracking comparison system")
    center(w)  # Move the window to a comfortable position
    w.ui.show()
    app.exec()

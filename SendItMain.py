import shutil
import time

from PyQt5.QtCore import QRect, QPropertyAnimation, QEasingCurve, QThread, QObject, pyqtSignal, QAbstractListModel, Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication, QMainWindow, QDialog, QLabel, QPushButton, QComboBox, QFileDialog, \
    QVBoxLayout, QProgressBar, QWidget, QTextEdit
from PyQt5 import uic, QtGui
import sys
import os
import json
import pathlib
import netifaces as ni
import random as rm
import socket

main_dir = pathlib.Path().absolute()
interface_file_path = str(main_dir) + "/interface.json"
ip_available = False

BROD_ADD = ""
HOME = os.getenv("HOME")
PORT = 4444
APP_CODE = "sendit004"
THIS_APP = "220"
RERUN_APP = 0
BACK_TO_APP = 1
FREE_SPACE = 0
MIN_VER = 210
REC_ADDR = None

SEARCH_CODE = APP_CODE + "/*Searching*/"
CONNCT_SIG = APP_CODE + "/*CONN_NOW*/"
ASK_CODE_SIG = APP_CODE + "/*ASK_CODE*/"
CONN_OK = APP_CODE + "/*CONN_OK*/"
WRONG_CODE = APP_CODE + "/*WRONG*/"
OLD_VER = APP_CODE + "/*OLD*/"
DEVICE_DETAILS = "DEVICEDETAILS"
NEXT_SIG = "/*ENTER_STEP2*/"
INTERFACE = ""

# sender variables
files = list()
skipThis = False
stopNow = False
STATUS_COMPLETE = 0
STATUS_ERROR = 1
STATUS_WAITING = 2
stopBytes = "sender_stop/*-222*/"
running = False
sent_in_sec = 0

# receiver variables
MY_IP = ""
isCodeSet = False
DIR = os.getenv("HOME") + "/sendit"
recvd_in_sec = 0
receiver_ok = "sendit004_OK"


def format_data(rec_bytes):
    if rec_bytes < 1024:
        return str(rec_bytes) + " B"
    if 1024 <= rec_bytes < 1048576:
        return str((rec_bytes / 1024).__round__()) + " kB"
    if 1048576 <= rec_bytes < 1073741824:
        in_mb = ((rec_bytes * 10 / 1048576).__round__()) / 10
        return str(in_mb) + " MB"
    else:
        in_gb = ((rec_bytes * 100 / 1073741824).__round__()) / 100
        return str(in_gb) + " GB"


def generate_code():
    global CODE
    a = rm.randint(0, 9)
    b = rm.randint(0, 9)
    c = rm.randint(0, 9)
    d = rm.randint(0, 9)
    CODE = str(a) + str(b) + str(c) + str(d)
    return CODE


def get_rId():
    main_dir = pathlib.Path().absolute()
    id_file_path = str(main_dir) + "/rid.json"
    if pathlib.Path(id_file_path).exists():
        with open(id_file_path) as file:
            data = json.load(file)
            rId = str(data['rid'])
            return rId
    else:
        rInt = rm.randint(10000000, 99999999)
        rId = str(rInt)
        with open(id_file_path, 'w') as file:
            data = {'rid': rId}
            json.dump(data, file)
        return rId


def get_free_space():
    return shutil.disk_usage("/")[2]


def get_interface_name():
    try:
        with open(interface_file_path) as file:
            data = json.load(file)
            interface_name = data['interface']
            return interface_name
    except Exception:
        return '-1'


def set_my_ip():
    global MY_IP
    try:
        with open(interface_file_path) as file:
            data = json.load(file)
            interface = data['interface']
            ips = ni.ifaddresses(interface)[ni.AF_INET]
            MY_IP = ips[0]['addr']
    except Exception:
        MY_IP = '-1'


class ReceiverTCP(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = uic.loadUi("receivertcp1.ui", self)
        self.beforAnimData = 0
        self.setWindowIcon(QtGui.QIcon('icon.png'))
        self.setWindowTitle("Send.it")
        self.setFixedWidth(800)
        self.setFixedHeight(550)

        # get dimensions of progressBar
        self.progX = self.progressBar.geometry().x()
        self.progY = self.progressBar.geometry().y()
        self.maxProg = self.progBackground.geometry().width()
        self.heightProg = self.progBackground.geometry().height()

        self.createWorker()

    class FileModel(QAbstractListModel):
        def __init__(self, *args, items=None, **kwargs):
            super().__init__(*args, **kwargs)
            self.tick = QtGui.QImage('tick.png')
            self.wait = QtGui.QImage('wait.png')
            self.cancel = QtGui.QImage('canceled.png')
            self.items = items or []

        def data(self, index, role):
            if role == Qt.DisplayRole:
                _, text = self.items[index.row()]
                return text
            if role == Qt.DecorationRole:
                status, _ = self.items[index.row()]
                if status == STATUS_COMPLETE:
                    return self.tick
                if status == STATUS_WAITING:
                    return self.wait
                if status == STATUS_ERROR:
                    return self.cancel

        def rowCount(self, index):
            return len(self.items)

    class FileManagerWorker(QObject):
        def run(self):
            print("fm started")
            os.system("xdg-open " + DIR)
            print("fm finished")

    class SpeedWorker(QObject):
        updateSignal = pyqtSignal(str)
        finishedSignal = pyqtSignal()

        def run(self):
            global recvd_in_sec
            while running:
                recvd_in_sec = 0
                time.sleep(1)
                self.updateSignal.emit(format_data(recvd_in_sec) + "/s")
            self.finishedSignal.emit()

    class TcpWorker(QObject):
        operationStatus = pyqtSignal(str)
        finishSignal = pyqtSignal()
        progressSignal = pyqtSignal(str)
        fileStatus = pyqtSignal(str, str)
        updateModel = pyqtSignal(int, int)
        allFinishSignal = pyqtSignal()

        def run(self):
            global recvd_in_sec, running
            print("tcp worker running")
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.bind((MY_IP, PORT))
                sock.listen(1)
                buffer_size = 4096
                file_row = 0
                running = True
                while running:
                    conn, address = sock.accept()
                    mode_str = str(conn.recv(buffer_size))
                    if not mode_str.__contains__(APP_CODE):
                        continue
                    sep_index = mode_str.index("/*")
                    last_index2 = mode_str.index("*/")
                    mode_code = mode_str[sep_index + 2:last_index2]
                    if mode_code.__contains__("stop"):
                        self.finishSignal.emit()
                        conn.send(bytes(receiver_ok, "utf-8"))
                        running = False
                        break
                    if mode_code.__contains__("files"):
                        #   print("receiving files on tcp:")
                        count_index = mode_code.index("#")
                        count = mode_code[count_index + 1:last_index2]
                        #   print("files available: ", count)
                        #  send ok
                        conn.send(bytes(receiver_ok, "utf-8"))
                        for file_count in range(0, int(count)):
                            stream = conn.recv(buffer_size)
                            name_str = str(stream)
                            sep_index = name_str.index('/*')
                            last_index1 = name_str.index('*/')
                            file_name = name_str[2:sep_index]
                            file_size = name_str[sep_index + 2:last_index1]
                            conn.send(bytes(receiver_ok, "utf-8"))
                            self.fileStatus.emit(file_name, file_size)
                            with open(DIR + "/" + file_name, 'wb') as file:
                                recd_data = 0
                                running = True
                                file_size_str = format_data(int(file_size))
                                loops = 0
                                while True:
                                    try:
                                        loops += 1
                                        conn.settimeout(3)
                                        file_data = conn.recv(buffer_size)
                                        file.write(file_data)
                                        recd_data += len(file_data)
                                        recvd_in_sec += len(file_data)
                                        if loops % 200 == 0:
                                            self.operationStatus.emit(str(recd_data))
                                            self.progressSignal.emit(str(recd_data))
                                        if recd_data == int(file_size):
                                            self.operationStatus.emit(str(recd_data))
                                            self.progressSignal.emit(str(recd_data))
                                            self.updateModel.emit(file_row, STATUS_COMPLETE)
                                            break
                                    except IOError as err:
                                        print("IOError:", err)
                                        self.updateModel.emit(file_row, STATUS_ERROR)
                                        break
                                final_response = bytes("sendit004_received/*" + str(get_free_space()) + "*/", "utf-8")
                                conn.send(final_response)
                            file_row += 1
                        self.allFinishSignal.emit()
            except IOError as err:
                print(err)

    def createWorker(self):
        self.model = self.FileModel()
        self.fileList.setModel(self.model)
        self.exitButton.clicked.connect(self.exitApp)
        self.tcpThread = QThread()
        self.tcpWorker = self.TcpWorker()
        self.tcpWorker.moveToThread(self.tcpThread)
        self.tcpThread.started.connect(self.tcpWorker.run)
        self.tcpThread.finished.connect(self.tcpThread.deleteLater)
        self.tcpWorker.finishSignal.connect(self.tcpThread.quit)
        self.tcpWorker.finishSignal.connect(self.tcpWorker.deleteLater)
        self.tcpWorker.operationStatus.connect(self.updateOperationLabel)
        self.tcpWorker.fileStatus.connect(self.updateFileInfo)
        self.tcpWorker.progressSignal.connect(self.updateProgress)
        self.tcpWorker.updateModel.connect(self.updateModel)
        self.tcpWorker.allFinishSignal.connect(self.onFinish)
        self.tcpWorker.finishSignal.connect(self.onSenderStop)
        self.spaceLabel.setText("Free Space : " + format_data(get_free_space()))

        self.speedThread = QThread()
        self.speedWorker = self.SpeedWorker()
        self.speedWorker.moveToThread(self.speedThread)
        self.speedThread.started.connect(self.speedWorker.run)
        self.speedThread.finished.connect(self.speedThread.deleteLater)
        self.speedWorker.finishedSignal.connect(self.speedThread.quit)
        self.speedWorker.finishedSignal.connect(self.speedWorker.deleteLater)
        self.speedWorker.updateSignal.connect(self.updateSpeed)

        self.tcpThread.start()
        self.speedThread.start()

    def updateModel(self, row, status):
        _, text = self.model.items[row]
        self.model.items[row] = (status, text)
        self.updateFreeSpace()
        self.model.layoutChanged.emit()

    def updateFileInfo(self, name, size):
        self.fileName = name
        self.fileSize = int(size)
        self.formattedSize = format_data(self.fileSize)
        self.model.items.append((STATUS_WAITING, name))
        self.model.layoutChanged.emit()

    def updateOperationLabel(self, data):
        self.operationLabel.setText(self.fileName + " : " + format_data(int(data)) + "/" + self.formattedSize)

    def updateProgress(self, data):
        #   prog = round(int(data) * 100 / self.fileSize)
        #   self.progressBar.setValue(prog)
        self.anim = QPropertyAnimation(self.progressBar, b"geometry")
        progressPoint = int(self.maxProg * int(data) / self.fileSize)
        self.anim.setDuration(100)
        self.anim.setStartValue(QRect(self.progX, self.progY, self.beforAnimData, self.heightProg))
        self.anim.setEndValue(QRect(self.progX, self.progY, progressPoint, self.heightProg))
        self.anim.start()
        self.beforAnimData = progressPoint

    def updateSpeed(self, text):
        self.speedLabel.setText(text)

    def updateFreeSpace(self):
        self.spaceLabel.setText("Free Space : " + format_data(get_free_space()))

    def onFinish(self):
        self.folderButton.setEnabled(True)
        self.fmThread = QThread()
        self.fmWorker = self.FileManagerWorker()
        self.fmWorker.moveToThread(self.fmThread)
        self.fmThread.started.connect(self.fmWorker.run)
        self.folderButton.clicked.connect(lambda: self.fmThread.start())

    def onSenderStop(self):
        self.progressBar.setEnabled(False)
        self.sDialog = QDialog()
        self.sDialog.setWindowTitle("Sender Stopped")
        self.sLabel = QLabel("Sender disconnected, no more files available to receive,\n You can EXIT now")
        self.sButton = QPushButton("OK")
        self.sButton.clicked.connect(lambda: self.sDialog.close())
        vBox = QVBoxLayout(self.sDialog)
        vBox.addWidget(self.sLabel)
        vBox.addWidget(self.sButton)
        self.sDialog.show()

    def exitApp(self):
        if running:
            self.cDialog = QDialog()
            uic.loadUi('setipdialog.ui', self.cDialog)
            self.cDialog.setWindowTitle("confirm exit")
            self.cDialog.ipboxlabel.setText("are you sure to stop the process?")
            self.cDialog.ipfixlabel.close()
            self.cDialog.ipEdit.close()
            self.cDialog.buttonBox.accepted.connect(self.destroyApp)
            self.cDialog.show()
        else:
            app.closeAllWindows()

    def destroyApp(self):
        self.tcpThread.quit()
        self.tcpThread.deleteLater()
        self.tcpWorker.deleteLater()
        self.destroy()


class ReceiverConnection(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = uic.loadUi("receiverconnection.ui", self)
        self.setWindowTitle("Send.it")
        self.setWindowIcon(QtGui.QIcon('icon.png'))
        self.setFixedHeight(250)
        self.setFixedWidth(300)
        self.label = QLabel("Waiting for sender..")
        self.label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        font = QFont()
        font.setPointSize(14)
        self.label.setFont(font)
        self.pBar = QProgressBar()
        self.pBar.setMaximum(0)
        self.pBar.setMinimum(0)
        self.vBox = QVBoxLayout()
        self.vBox.addWidget(self.label)
        self.vBox.addWidget(self.pBar)
        self.centralWidget = QWidget()
        self.setCentralWidget(self.centralWidget)
        self.centralWidget.setLayout(self.vBox)
        print(MY_IP)
        if MY_IP == "-1":
            self.showErrorDialog("No ip found")
        else:
            self.prepareWorker()

    class UdpWorker(QObject):
        changeUI = pyqtSignal(str)
        finishSignal = pyqtSignal(int)
        errorSignal = pyqtSignal(str)

        def run(self):
            global isCodeSet, Sender_name
            exitCode = 0
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.bind(('', PORT))
                print("socket bond")
                firstStep = True
                while firstStep:
                    data, addr = sock.recvfrom(4096)
                    msg = str(data)
                    print(msg)
                    if msg.__contains__(SEARCH_CODE):
                        print("sender searching")
                        response = bytes(
                            APP_CODE + "/*" + socket.gethostname() + "*/", "utf-8"
                        )
                        sock.sendto(response, addr)
                        print("handshake send")
                        continue
                    if msg.__contains__(NEXT_SIG):
                        print("Entering in next step")
                        nameIndex = msg.index("#")
                        endIndex = msg.index("/*")
                        Sender_name = msg[nameIndex + 1: endIndex]
                        sock.close()
                        firstStep = False
                        continue
                #  in step 2
                newSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                print("Listening on new socket")
                newSock.bind(('', PORT))
                msg2, addr = newSock.recvfrom(1024)
                msgs2 = str(msg2)
                print(msgs2)
                if msgs2.__contains__(CONNCT_SIG):
                    print("Connect signal found")
                    rId = get_rId()
                    free = str(shutil.disk_usage("/")[2])
                    connSig = bytes(rId + "/*" + free + "*/" + THIS_APP + "@", "utf-8")
                    newSock.sendto(connSig, addr)
                    print("mac address sent")
                    conMesg, _ = newSock.recvfrom(1024)
                    conMsg = str(conMesg)
                    print(conMsg)
                    if conMsg.__contains__(ASK_CODE_SIG):
                        print("code will be asked here")
                        self.changeUI.emit(Sender_name)
                        while not isCodeSet:
                            _
                        codeStr = bytes(APP_CODE + "&" + RES_CODE + "/*" + str(
                            shutil.disk_usage("/")[2]) + "*/", "utf-8")
                        newSock.sendto(codeStr, addr)
                        response, _ = newSock.recvfrom(1024)
                        resStr = str(response)
                        if resStr.__contains__(CONN_OK):
                            print("Connected finished")
                        else:
                            print("wrong code sent")
                            self.errorSignal.emit("Wrong code sent, app will terminate")
                            exitCode = 1
                    if conMsg.__contains__(CONN_OK):
                        print("Connected ok")
                    if conMsg.__contains__(OLD_VER):
                        print("Old version error")
                        self.errorSignal.emit("You are using old version, could not continue")
                        exitCode = 1
                newSock.close()
            except IOError as err:
                self.errorSignal.emit(str(err))
                exitCode = 1
            self.finishSignal.emit(exitCode)

    def get_broadcast_address(self):
        try:
            main_dir = pathlib.Path().absolute()
            interface_file_path = str(main_dir) + "/interface.json"
            with open(interface_file_path) as file:
                data = json.load(file)
                interface = data['interface']
                ips = ni.ifaddresses(interface)[ni.AF_INET]
                ip = ips[0]['broadcast']
                return ip
        except Exception:
            return '-1'

    def prepareWorker(self):
        self.udpThread = QThread()
        self.udpWorker = self.UdpWorker()
        self.udpWorker.moveToThread(self.udpThread)
        self.udpThread.started.connect(self.udpWorker.run)
        self.udpThread.finished.connect(self.udpThread.deleteLater)
        self.udpWorker.finishSignal.connect(self.udpThread.quit)
        self.udpWorker.finishSignal.connect(self.udpWorker.deleteLater)
        self.udpWorker.finishSignal.connect(self.start_ReceiverTCP)
        self.udpWorker.changeUI.connect(self.changeUI)
        self.udpWorker.errorSignal.connect(self.showErrorDialog)
        self.udpThread.start()

    def changeUI(self, name):
        self.label.setText("Please enter code to connect to\n" + name)
        self.pBar.close()
        self.textEdit = QTextEdit(self)
        font = QFont()
        font.setPointSize(30)
        self.textEdit.setFont(font)
        self.textEdit.setFixedHeight(60)
        self.textEdit.setFixedWidth(115)
        self.textEdit.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.setButton = QPushButton("OK", self)
        self.setButton.clicked.connect(self.setCodes)
        self.vBox.addWidget(self.textEdit, 0, (Qt.AlignHCenter | Qt.AlignVCenter))
        self.vBox.addWidget(self.setButton, 0, (Qt.AlignHCenter | Qt.AlignVCenter))

    def setCodes(self):
        global RES_CODE, isCodeSet
        RES_CODE = self.textEdit.toPlainText()
        isCodeSet = True

    def start_ReceiverTCP(self, exitCode):
        if exitCode == 0:
            receiver_tcp = ReceiverTCP()
            receiver_tcp.show()
            self.close()
        else:
            self.hide()

    def showErrorDialog(self, error):
        self.dialog1 = QDialog(self)
        self.dialog1.resize(300, 100)
        self.dialog1.setWindowTitle("Error")
        label = QLabel(error)
        okBtn = QPushButton("OK")
        okBtn.clicked.connect(lambda: self.dialog1.close())
        vLayout = QVBoxLayout(self.dialog1)
        vLayout.addWidget(label)
        vLayout.addWidget(okBtn)
        self.dialog1.show()


class SenderTCP(QMainWindow):
    class SpeedWorker(QObject):
        updateSignal = pyqtSignal(str)
        finishedSignal = pyqtSignal()

        def run(self):
            global sent_in_sec
            while True:
                sent_in_sec = 0
                time.sleep(1)
                self.updateSignal.emit(format_data(sent_in_sec) + "/s")
                if not running:
                    break
            self.finishedSignal.emit()

    class TCPWorker(QObject):
        progSignal = pyqtSignal(str)
        progSignal2 = pyqtSignal(float)
        fileFinishSignal = pyqtSignal(int, int)
        allSentSignal = pyqtSignal()
        errorSignal = pyqtSignal(str)
        spaceSignal = pyqtSignal()
        finishSignal = pyqtSignal()
        skipThis = False
        stopNow = False
        stopBytes = "sender_stop/*-222*/"
        running = False
        STATUS_COMPLETE = 0
        STATUS_ERROR = 1
        STATUS_WAITING = 2

        def run(self):
            global FREE_SPACE, files, stopNow, skipThis, sent_in_sec, running
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((REC_ADDR[0], REC_ADDR[1]))
            try:
                file_codes = bytes(APP_CODE + "/*files#" + str(len(files)) + "*/", "utf-8")
                sock.sendall(file_codes, 0)
                res = str(sock.recv(1024))
                if res.__contains__("OK"):
                    running = True
                    fileCount = 0
                    stopNow = False
                    for file_path in files:
                        filename = os.path.basename(file_path)
                        file_size = os.path.getsize(file_path)
                        skipThis = False
                        if stopNow:
                            stop_bytes = bytes(stopBytes, "utf-8")
                            sock.sendall(stop_bytes)
                            break
                        if file_size > FREE_SPACE:
                            self.errorSignal.emit(f"Receiver does not have free space to receive {filename},\n"
                                                  f"file was skipped, available {format_data(FREE_SPACE)}")
                            skipThis = True
                        file_size_str_main = str(file_size)
                        file_info_bytes = bytes(filename + "/*" + file_size_str_main + "*/", "utf-8")
                        sock.sendall(file_info_bytes, 0)
                        sock.recv(1024)
                        with open(file_path, 'rb') as file_input:
                            sent_bytes = 0
                            file_size_str = format_data(file_size)
                            loops = 0
                            while True:
                                if stopNow or skipThis:
                                    break
                                loops += 1
                                bytes_read = file_input.read(4096)
                                if not bytes_read:
                                    break
                                sock.sendall(bytes_read)
                                sent_bytes += len(bytes_read)
                                sent_in_sec += len(bytes_read)
                                if loops % 200 == 0:
                                    self.progSignal.emit(
                                        filename + ":  " + format_data(sent_bytes) + "/" + file_size_str)
                                    self.progSignal2.emit(sent_bytes / file_size)
                            self.progSignal2.emit(sent_bytes / file_size)
                            self.progSignal.emit(filename + ":  " + format_data(sent_bytes) + "/" + file_size_str)
                            final = str(sock.recv(1024))
                            if final.__contains__("sendit004_received"):
                                sep_index = final.index("/*")
                                end_index = final.index("*/")
                                FREE_SPACE = int(final[sep_index + 2:end_index])
                                if skipThis or stopNow:
                                    self.fileFinishSignal.emit(fileCount, STATUS_ERROR)
                                else:
                                    self.fileFinishSignal.emit(fileCount, STATUS_COMPLETE)
                            else:
                                print("error while receiving final response")
                        fileCount += 1
                        self.spaceSignal.emit()
                    self.allSentSignal.emit()
            except IOError as err1:
                self.errorSignal.emit(err1)
            sock.close()
            running = False
            self.finishSignal.emit()

    class FileModel(QAbstractListModel):
        def __init__(self, *args, items=None, **kwargs):
            super().__init__(*args, **kwargs)
            self.tick = QtGui.QImage('tick.png')
            self.wait = QtGui.QImage('wait.png')
            self.cancel = QtGui.QImage('canceled.png')
            self.items = items or []

        def data(self, index, role):
            if role == Qt.DisplayRole:
                _, text = self.items[index.row()]
                return text
            if role == Qt.DecorationRole:
                status, _ = self.items[index.row()]
                if status == STATUS_COMPLETE:
                    return self.tick
                if status == STATUS_WAITING:
                    return self.wait
                if status == STATUS_ERROR:
                    return self.cancel

        def rowCount(self, index):
            return len(self.items)

    def __init__(self):
        super().__init__()
        uic.loadUi("sendertcp1.ui", self)
        self.setWindowTitle("Send.it")
        self.setWindowIcon(QtGui.QIcon('icon.png'))
        self.setFixedWidth(785)
        self.setFixedHeight(530)
        self.beforAnimData = 0

        # get dimensions of progressBar
        self.progX = self.progressBar.geometry().x()
        self.progY = self.progressBar.geometry().y()
        self.maxProg = self.progBackground.geometry().width()
        self.heightProg = self.progBackground.geometry().height()

        self.fileStrs = list()
        self.speedLabel.setText("")
        self.openButton.clicked.connect(self.openFileDialog)
        self.exitButton.clicked.connect(lambda: self.destroy())
        self.showAvailableSpace()
        self.setAcceptDrops(True)

        # variables
        self.running = False
        self.STATUS_COMPLETE = 0
        self.STATUS_ERROR = 1
        self.STATUS_WAITING = 2

    def prepareWorker(self):
        global files
        files = self.fileStrs
        self.model = self.FileModel()
        self.fileList.setModel(self.model)
        self.set_Model()
        # self.progressBar.setEnabled(True)
        self.stopButton.setEnabled(True)
        self.skipButton.setEnabled(True)
        self.openButton.setEnabled(False)
        self.exitButton.setEnabled(False)
        self.speedLabel.setEnabled(True)
        self.dropInfo.setText('')
        self.stopButton.clicked.connect(self.stopSending)
        self.skipButton.clicked.connect(self.skipFile)
        self.tcpThrad = QThread()
        self.tcpWorker = self.TCPWorker()
        self.tcpWorker.moveToThread(self.tcpThrad)
        self.tcpThrad.started.connect(self.tcpWorker.run)
        self.tcpWorker.finishSignal.connect(self.tcpThrad.quit)
        self.tcpThrad.finished.connect(self.tcpThrad.deleteLater)
        self.tcpWorker.finishSignal.connect(self.tcpWorker.deleteLater)
        self.tcpWorker.progSignal.connect(self.showProgress)
        self.tcpWorker.progSignal2.connect(self.updateProgressBar)
        self.tcpWorker.fileFinishSignal.connect(self.updateModel)
        self.tcpWorker.allSentSignal.connect(self.backToNormal)
        self.tcpWorker.errorSignal.connect(self.showErrorDialog)
        self.tcpWorker.spaceSignal.connect(self.showAvailableSpace)

        self.speedThread = QThread()
        self.speedWorker = self.SpeedWorker()
        self.speedWorker.moveToThread(self.speedThread)
        self.speedThread.started.connect(self.speedWorker.run)
        self.speedThread.finished.connect(self.speedThread.deleteLater)
        self.speedWorker.finishedSignal.connect(self.speedThread.quit)
        self.speedWorker.finishedSignal.connect(self.speedWorker.deleteLater)
        self.speedWorker.updateSignal.connect(self.updateSpeed)

        self.tcpThrad.start()
        self.speedThread.start()

    def openFileDialog(self):
        self.fileStrs.clear()
        self.fileStrs, _ = QFileDialog.getOpenFileNames(self, "QDialog.getOpenFileName()", HOME, "All files (*)")
        if len(self.fileStrs) == 0:
            return
        else:
            self.prepareWorker()

    def dragEnterEvent(self, a0):
        a0.accept()
        self.dropInfo.setText("Drop files here to send")

    def dropEvent(self, a0):
        self.fileStrs.clear()
        a0.accept()
        self.dropInfo.setText("")
        if a0.mimeData().hasUrls:
            for url in a0.mimeData().urls():
                self.fileStrs.append(url.toLocalFile())
            self.prepareWorker()

    def showProgress(self, prog):
        self.fileOperationLabel.setText(prog)

    def updateProgressBar(self, data):
        self.anim = QPropertyAnimation(self.progressBar, b"geometry")
        progressPoint = int(data * self.maxProg)
        self.anim.setDuration(100)
        self.anim.setStartValue(QRect(self.progX, self.progY, self.beforAnimData, self.heightProg))
        self.anim.setEndValue(QRect(self.progX, self.progY, progressPoint, self.heightProg))
        self.anim.start()
        self.beforAnimData = progressPoint

    def set_Model(self):
        for fileStr in self.fileStrs:
            filename = os.path.basename(fileStr)
            self.model.items.append((2, filename))
            self.model.layoutChanged.emit()

    def updateModel(self, count, status):
        _, text = self.model.items[count]
        self.model.items[count] = (status, text)
        self.model.layoutChanged.emit()

    def skipFile(self):
        global skipThis
        skipThis = True

    def stopSending(self):
        global stopNow
        stopNow = True

    def backToNormal(self):
        # self.progressBar.setEnabled(False)
        self.stopButton.setEnabled(False)
        self.skipButton.setEnabled(False)
        self.openButton.setEnabled(True)
        self.exitButton.setEnabled(True)
        self.speedLabel.setEnabled(False)

    def updateSpeed(self, text):
        self.speedLabel.setText(text)

    def showAvailableSpace(self):
        self.spaceLabel.setText(f"Available space: {format_data(FREE_SPACE)}")

    def showErrorDialog(self, error):
        self.dialog = QDialog(self)
        self.dialog.resize(300, 100)
        self.dialog.setWindowTitle("Error")
        label = QLabel(error)
        okBtn = QPushButton("OK")
        okBtn.clicked.connect(lambda: self.dialog.close())
        vLayout = QVBoxLayout(self.dialog)
        vLayout.addWidget(label)
        vLayout.addWidget(okBtn)
        self.dialog.show()


class SenderConnection(QMainWindow):

    def __init__(self):
        super().__init__()
        self.ui = uic.loadUi("senderconnection.ui", self)
        self.windowWidth = 315
        self.setWindowTitle("Send.it")
        self.setWindowIcon(QtGui.QIcon('icon.png'))
        self.setGeometry(QRect(int(screenWidth / 2.5), int(screenHeight / 2.5), self.windowWidth, 200))
        self.setUpUI()

    class UDPWorker(QObject):
        showCode = pyqtSignal(str)
        showReceiver = pyqtSignal(str, str)
        errorSignal = pyqtSignal(str, int)
        finishedSignal = pyqtSignal()
        nextSignal = pyqtSignal()

        def run(self):
            global FREE_SPACE, REC_ADDR, step1
            d_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            d_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            try:
                brd_add = ('<broadcast>', PORT)
                step1 = True
                receivers = []
                search_bytes = bytes(SEARCH_CODE, "utf-8")
                d_socket.sendto(search_bytes, brd_add)
                while step1:
                    try:
                        d_socket.settimeout(3)
                        search_bytes = bytes(SEARCH_CODE, "utf-8")
                        d_socket.sendto(search_bytes, brd_add)
                        print("search sent")
                        msg, addr = d_socket.recvfrom(1024)
                        print(str(msg), addr[0])
                        msg1 = str(msg)
                        nameStart = msg1.index("/*")
                        lastIndex = msg1.index("*/")
                        name = msg1[nameStart + 2:lastIndex]
                        if not receivers.__contains__(name):
                            receivers.append(name)
                            self.showReceiver.emit(name, addr[0])
                        time.sleep(3)
                    except IOError as er:
                        print(er)

                #  in step 2
                REC_ADDR = (receiverAddress, PORT)
                print("Entering in step2")
                next_sig = bytes(str(APP_CODE + "#" + socket.gethostname() + NEXT_SIG), "utf-8")
                d_socket.sendto(next_sig, REC_ADDR)
                print(str(next_sig) + "to :", str(REC_ADDR))
                con_sig = bytes(CONNCT_SIG, "utf-8")
                d_socket.sendto(con_sig, REC_ADDR)
                print(str(con_sig) + "to: ", str(REC_ADDR))

                # in step 3
                detailsReceived = False
                while not detailsReceived:
                    msg, _ = d_socket.recvfrom(1024)
                    msg2 = str(msg)
                    print("details: ", msg2)
                    if msg2.__contains__(DEVICE_DETAILS):
                        startIndex = msg2.index("#")
                        freeIndex = msg2.index("/*")
                        verIndex = msg2.index("*/")
                        endIndex = msg2.index("@")
                        rId = msg2[startIndex + 1:freeIndex]
                        free = msg2[freeIndex + 2:verIndex]
                        FREE_SPACE = int(free)
                        ver = msg2[verIndex + 2:endIndex]
                        detailsReceived = True

                if int(ver) < MIN_VER:
                    old_ver_Signal = bytes(OLD_VER, 'utf-8')
                    d_socket.sendto(old_ver_Signal, REC_ADDR)

                oldDevice = False
                # set_device_file()
                if pathlib.Path(deviceFile).exists():
                    print("existing file will be handleed here")
                    if pathlib.Path(deviceFile).exists():
                        with open(deviceFile) as file:
                            try:
                                data = json.load(file)
                                saved_id = data[receiverName]
                                if saved_id == rId:
                                    oldDevice = True
                                    #   store_receiver_address(rec_add)
                                    okSignal = bytes(CONN_OK, 'utf-8')
                                    d_socket.sendto(okSignal, REC_ADDR)
                                    self.nextSignal.emit()
                                    self.finishedSignal.emit()
                            except:
                                oldDevice = False

                if not oldDevice:
                    ask_code_sig = bytes(ASK_CODE_SIG, "utf-8")
                    d_socket.sendto(ask_code_sig, REC_ADDR)
                    print("code ask signal sent")
                    new_code = generate_code()
                    self.showCode.emit(new_code)
                    d_socket.settimeout(30)
                    code_bytes, _ = d_socket.recvfrom(1024)
                    code_str = str(code_bytes)
                    codeIndex = code_str.index("&")
                    freeIndex1 = code_str.index("/*")

                    code = code_str[codeIndex + 1:freeIndex1]
                    if code == new_code:
                        #   store_receiver_address(rec_add)
                        okSignal = bytes(CONN_OK, 'utf-8')
                        d_socket.sendto(okSignal, REC_ADDR)
                        # update device list
                        if not pathlib.Path(deviceFile).exists():
                            with open(deviceFile, 'w') as newFile:
                                data = {receiverName: rId}
                                json.dump(data, newFile)
                        else:
                            print("json file will be udpated")
                            with open(deviceFile) as oldFile:
                                data = json.load(oldFile)
                                data[receiverName] = rId
                                with open(deviceFile, 'w') as newFile:
                                    json.dump(data, newFile)
                        self.nextSignal.emit()
                        self.finishedSignal.emit()
                    else:
                        wrongSignal = bytes(WRONG_CODE, 'utf-8')
                        d_socket.sendto(wrongSignal, REC_ADDR)

            except IOError as err:
                self.errorSignal.emit("Error: " + str(err), RERUN_APP)
                self.finishedSignal.emit()

    def setUpUI(self):
        self.udpThread = QThread()
        self.udpWorker = self.UDPWorker()
        self.udpWorker.moveToThread(self.udpThread)
        self.udpThread.started.connect(self.udpWorker.run)
        self.udpWorker.finishedSignal.connect(self.udpThread.quit)
        self.udpWorker.finishedSignal.connect(self.udpWorker.deleteLater)
        self.udpWorker.finishedSignal.connect(self.udpThread.deleteLater)
        self.udpWorker.showCode.connect(self.showCodeOnUI)
        self.udpWorker.showReceiver.connect(self.showReceiver)
        self.udpWorker.errorSignal.connect(self.showErrorDialog)
        self.udpWorker.nextSignal.connect(self.go_to_nextUI)
        self.udpThread.start()
        self.set_device_file()

    def showReceiver(self, btnName, addr):
        receiverButton = QPushButton(btnName)
        self.receiverLayout.addWidget(receiverButton)
        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(100)
        self.anim.setStartValue(
            QRect(self.geometry().x(), self.geometry().y(), self.windowWidth, self.geometry().height()))
        self.anim.setEasingCurve(QEasingCurve.OutExpo)
        self.anim.setEndValue(QRect(self.geometry().x(), self.geometry().y(), self.windowWidth, 400))
        self.anim.start()
        receiverButton.clicked.connect(lambda: self.set_receiver_details(btnName, addr))

    def set_receiver_details(self, name, address):
        global receiverName, receiverAddress, step1
        receiverName = name
        receiverAddress = address
        step1 = False
        self.labelMain.setText("Connecting to " + receiverName)
        #   self.setFixedHeight(200)
        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(100)
        self.anim.setEasingCurve(QEasingCurve.InExpo)
        self.anim.setStartValue(
            QRect(self.geometry().x(), self.geometry().y(), self.windowWidth, self.geometry().height()))
        self.anim.setEndValue(QRect(self.geometry().x(), self.geometry().y(), self.windowWidth, 200))
        self.anim.start()

    def showCodeOnUI(self, code_text):
        self.labelMain.setText("Enter below code to connect to this machine")
        self.progressBar.close()
        self.codeLabel.setText(code_text)

    def showErrorDialog(self, error, bAct):
        eDialog = QDialog(self)
        uic.loadUi("errordialog.ui", eDialog)
        eDialog.setWindowTitle("Error")
        eDialog.errorLabel.setText(error)

        if bAct == RERUN_APP:
            eDialog.buttonBox.accepted.connect(lambda: self.close_application(True))
            eDialog.buttonBox.rejected.connect(lambda: self.close_application(False))
        else:
            eDialog.buttonBox.rejected.connect(lambda: self.close_application(False))
        eDialog.show()

    def get_broadcast_address(self):
        try:
            main_dir = pathlib.Path().absolute()
            interface_file_path = str(main_dir) + "/interface.json"
            with open(interface_file_path) as file:
                data = json.load(file)
                interface = data['interface']
                ips = ni.ifaddresses(interface)[ni.AF_INET]
                ip = ips[0]['broadcast']
                return ip
        except Exception:
            return '-1'

    def set_device_file(self):
        global deviceFile
        main_dir = pathlib.Path().absolute()
        deviceFile = str(main_dir) + "/devices.json"

    def go_to_nextUI(self):
        senderTCP = SenderTCP()
        senderTCP.show()
        self.close()

    def close_application(self, rerun):
        app.closeAllWindows()
        if rerun:
            os.system("python3 SenderConnection.py")


class MainUI(QMainWindow):
    def __init__(self):
        global ip_available
        super().__init__()
        main_dir = pathlib.Path().absolute()
        self.ip_file_path = str(main_dir) + "/myip.json"
        self.interface_file_path = str(main_dir) + "/interface.json"
        self.ui = uic.loadUi("senditmain1.ui", self)
        self.setWindowTitle("Send.it")
        #   self.setFixedWidth(208)
        #   self.setFixedHeight(230)
        self.setWindowIcon(QtGui.QIcon('icon.png'))
        self.sendIcon.clicked.connect(self.start_sender)
        self.receiveIcon.clicked.connect(self.start_receiver)
        self.editIcon.clicked.connect(self.showInterfaceDialog)
        #   self.dialog = QDialog()
        #   self.dUi = uic.loadUi("setipdialog.ui", self.dialog)
        #   self.dialog.setWindowTitle("Set Your IP Address")
        if MY_IP == "-1":
            self.label_2.setText("IP address not found,\n Please check the connection or change the INTERFACE")
        else:
            ip_available = True
            self.label_2.setText("My IP: " + MY_IP)

    def showInterfaceDialog(self):
        self.interfaceDialog = QDialog()
        uic.loadUi("interface.ui", self.interfaceDialog)
        self.interfaceDialog.setWindowTitle("Select Interface")
        self.interfaceDialog.currentLabel.setText(f"Current Value: {INTERFACE}")
        self.interfaceDialog.show()
        nets = ni.interfaces()
        for net in nets:
            if net != "lo":
                self.interfaceDialog.comboBox.addItem(str(net))
        self.interfaceDialog.comboBox.currentIndexChanged[str].connect(self.get_interface)
        cBox = QComboBox()
        cBox.currentText()
        self.interfaceDialog.buttonBox.accepted.connect(
            lambda: self.store_interface(self.interfaceDialog.comboBox.currentText()))
        print(nets)

    def get_interface(self, s):
        self.interfaceDialog.buttonBox.accepted.connect(lambda: self.store_interface(s))
        try:
            ips = ni.ifaddresses(s)[ni.AF_INET]
            addr = ips[0]['addr']
            subnet = ips[0]['netmask']
            broadcast = ips[0]['broadcast']
            ipInfo = "Ip Address: " + addr + "\nsubnet: " + subnet + "\nbroadcast: " + broadcast
            self.interfaceDialog.ipLabel.setText("")
            self.interfaceDialog.ipLabel.setText(ipInfo)
            print(s)
        except Exception as e:
            self.interfaceDialog.ipLabel.setText("")
            self.interfaceDialog.ipLabel.setText("Not all information found")
            print(e)

    def store_interface(self, interface_name):
        global ip_available, INTERFACE
        set_my_ip()
        with open(self.interface_file_path, 'w') as file:
            data = {'interface': interface_name}
            json.dump(data, file)
            print("interface stored")
            INTERFACE = interface_name
        if MY_IP == "-1":
            self.label_2.setText("IP address not found,\n Please check the connection or change the INTERFACE")
        else:
            ip_available = True
            self.label_2.setText(f"My IP: {MY_IP}")
            self.interfaceDialog.close()

    def start_sender(self):
        if ip_available:
            sender_connection = SenderConnection()
            sender_connection.show()
            self.close()
        else:
            dialog = QDialog(win)
            dialog.setWindowTitle("Error")
            dialog.setFixedHeight(100)
            dialog.setFixedWidth(400)
            label = QLabel("Error: ", dialog)
            label.setContentsMargins(10, 10, 10, 10)
            label.setText("Connection Not Found, \n Please check your connection or try to change network interface")
            btn = QPushButton(dialog)
            btn.setText("OK")
            btn.setGeometry(150, 50, 100, 30)
            btn.clicked.connect(dialog.close)
            dialog.show()

    def start_receiver(self):
        if ip_available:
            receiver_connection = ReceiverConnection()
            receiver_connection.show()
            self.close()
        else:
            dialog = QDialog(win)
            dialog.setWindowTitle("Error")
            dialog.setFixedHeight(100)
            dialog.setFixedWidth(400)
            label = QLabel("Error: ", dialog)
            label.setContentsMargins(10, 10, 10, 10)
            label.setText("Connection Not Found, \n Please check your connection or try to change network interface")
            btn = QPushButton(dialog)
            btn.setText("OK")
            btn.setGeometry(150, 50, 100, 30)
            btn.clicked.connect(dialog.close)
            dialog.show()


app = QApplication(sys.argv)
screenWidth = app.primaryScreen().size().width()
screenHeight = app.primaryScreen().size().height()
INTERFACE = get_interface_name()
set_my_ip()
win = MainUI()
win.show()
app.exec()

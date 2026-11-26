"use client"

import { forwardRef, type ForwardRefExoticComponent, type RefAttributes } from "react"
import { HugeiconsIcon, type HugeiconsProps, type IconSvgElement } from "@hugeicons/react"
import {
  Alert02Icon,
  AlertCircleIcon,
  ArrowDown01Icon,
  ArrowDown02Icon,
  ArrowLeft01Icon,
  ArrowLeft02Icon,
  ArrowRight01Icon,
  ArrowRight02Icon,
  ArrowUp02Icon,
  ArrowUpDownIcon,
  ArrowUpRight01Icon,
  AtIcon,
  Attachment01Icon,
  AudioWave01Icon,
  BubbleChatAddIcon,
  Cancel01Icon,
  CancelCircleIcon,
  CheckmarkCircle02Icon,
  CircleIcon,
  ClapperboardIcon,
  Clock01Icon,
  ComputerIcon,
  Copy01Icon,
  CropIcon,
  Delete02Icon,
  Download04Icon,
  File02Icon,
  FileRemoveIcon,
  Film01Icon,
  FingerPrintIcon,
  FlashIcon,
  FloppyDiskIcon,
  Folder01Icon,
  FolderLibraryIcon,
  FolderOpenIcon,
  Globe02Icon,
  GridViewIcon,
  HelpCircleIcon,
  Home01Icon,
  Image01Icon,
  InformationCircleIcon,
  Layers01Icon,
  LeftToRightListBulletIcon,
  LibraryIcon,
  LinkSquare02Icon,
  Linkedin01Icon,
  Loading03Icon,
  Login01Icon,
  Logout01Icon,
  MagicWand01Icon,
  Maximize02Icon,
  Menu01Icon,
  Mic01Icon,
  Mic02Icon,
  Minimize02Icon,
  MinusSignCircleIcon,
  Moon02Icon,
  MoreHorizontalIcon,
  MoreVerticalIcon,
  MusicNote03Icon,
  Notification01Icon,
  PaintBoardIcon,
  PauseIcon,
  PencilEdit02Icon,
  PlayIcon,
  PlusSignIcon,
  QuoteDownIcon,
  RefreshIcon,
  RotateCcwIcon,
  ScanIcon,
  Search01Icon,
  Settings01Icon,
  SidebarLeftIcon,
  SidebarRightIcon,
  SlidersHorizontalIcon,
  SparklesIcon,
  StopIcon,
  Sun03Icon,
  Target02Icon,
  TextIcon,
  ThumbsDownIcon,
  ThumbsUpIcon,
  Tick02Icon,
  TranslateIcon,
  UnavailableIcon,
  Undo02Icon,
  Upload04Icon,
  UserIcon,
  Video01Icon,
  VolumeHighIcon,
  VolumeMute02Icon,
  WorkflowSquare10Icon,
  ZoomInIcon,
  ZoomOutIcon,
} from "@hugeicons/core-free-icons"

/** AffectUI iconography stroke weight (matches AppShell, IconButton, EmptyState). */
export const AFFECTUI_ICON_STROKE = 1.9

export type AppIconProps = Omit<HugeiconsProps, "icon">
export type AppIcon = ForwardRefExoticComponent<AppIconProps & RefAttributes<SVGSVGElement>>

function createAppIcon(icon: IconSvgElement, displayName: string): AppIcon {
  const Component = forwardRef<SVGSVGElement, AppIconProps>(
    ({ strokeWidth = AFFECTUI_ICON_STROKE, size = 24, ...rest }, ref) => (
      <HugeiconsIcon
        ref={ref}
        icon={icon}
        size={size}
        strokeWidth={strokeWidth}
        {...rest}
      />
    ),
  )
  Component.displayName = displayName
  return Component
}

export const AlertCircle = createAppIcon(AlertCircleIcon, "AlertCircle")
export const ArrowDown = createAppIcon(ArrowDown02Icon, "ArrowDown")
export const ArrowDownIcon = createAppIcon(ArrowDown02Icon, "ArrowDownIcon")
export const ArrowLeft = createAppIcon(ArrowLeft02Icon, "ArrowLeft")
export const ArrowRight = createAppIcon(ArrowRight02Icon, "ArrowRight")
export const ArrowUp = createAppIcon(ArrowUp02Icon, "ArrowUp")
export const ArrowUpDown = createAppIcon(ArrowUpDownIcon, "ArrowUpDown")
export const ArrowUpRight = createAppIcon(ArrowUpRight01Icon, "ArrowUpRight")
export const AtSign = createAppIcon(AtIcon, "AtSign")
export const AudioLines = createAppIcon(AudioWave01Icon, "AudioLines")
export const Ban = createAppIcon(UnavailableIcon, "Ban")
export const Bell = createAppIcon(Notification01Icon, "Bell")
export const Check = createAppIcon(Tick02Icon, "Check")
export const CheckCircle2 = createAppIcon(CheckmarkCircle02Icon, "CheckCircle2")
export const ChevronDown = createAppIcon(ArrowDown01Icon, "ChevronDown")
export const ChevronLeft = createAppIcon(ArrowLeft01Icon, "ChevronLeft")
export const ChevronRight = createAppIcon(ArrowRight01Icon, "ChevronRight")
export const Circle = createAppIcon(CircleIcon, "Circle")
export const CircleCheck = createAppIcon(CheckmarkCircle02Icon, "CircleCheck")
export const CircleCheckIcon = createAppIcon(CheckmarkCircle02Icon, "CircleCheckIcon")
export const CircleHelp = createAppIcon(HelpCircleIcon, "CircleHelp")
export const Clapperboard = createAppIcon(ClapperboardIcon, "Clapperboard")
export const Copy = createAppIcon(Copy01Icon, "Copy")
export const Crop = createAppIcon(CropIcon, "Crop")
export const Crosshair = createAppIcon(Target02Icon, "Crosshair")
export const Download = createAppIcon(Download04Icon, "Download")
export const Ellipsis = createAppIcon(MoreHorizontalIcon, "Ellipsis")
export const EllipsisVertical = createAppIcon(MoreVerticalIcon, "EllipsisVertical")
export const ExternalLink = createAppIcon(LinkSquare02Icon, "ExternalLink")
export const FileText = createAppIcon(File02Icon, "FileText")
export const FileWarning = createAppIcon(FileRemoveIcon, "FileWarning")
export const Film = createAppIcon(Film01Icon, "Film")
export const Fingerprint = createAppIcon(FingerPrintIcon, "Fingerprint")
export const Folder = createAppIcon(Folder01Icon, "Folder")
export const FolderKanban = createAppIcon(FolderLibraryIcon, "FolderKanban")
export const FolderOpen = createAppIcon(FolderOpenIcon, "FolderOpen")
export const Globe = createAppIcon(Globe02Icon, "Globe")
export const History = createAppIcon(Clock01Icon, "History")
export const Home = createAppIcon(Home01Icon, "Home")
export const Image = createAppIcon(Image01Icon, "Image")
export const Info = createAppIcon(InformationCircleIcon, "Info")
export const InfoIcon = createAppIcon(InformationCircleIcon, "InfoIcon")
export const Languages = createAppIcon(TranslateIcon, "Languages")
export const Layers = createAppIcon(Layers01Icon, "Layers")
export const LayoutGrid = createAppIcon(GridViewIcon, "LayoutGrid")
export const Library = createAppIcon(LibraryIcon, "Library")
export const Linkedin = createAppIcon(Linkedin01Icon, "Linkedin")
export const List = createAppIcon(LeftToRightListBulletIcon, "List")
export const Loader2 = createAppIcon(Loading03Icon, "Loader2")
export const Loader2Icon = createAppIcon(Loading03Icon, "Loader2Icon")
export const LogIn = createAppIcon(Login01Icon, "LogIn")
export const LogOut = createAppIcon(Logout01Icon, "LogOut")
export const Maximize2 = createAppIcon(Maximize02Icon, "Maximize2")
export const Menu = createAppIcon(Menu01Icon, "Menu")
export const MessageSquarePlus = createAppIcon(BubbleChatAddIcon, "MessageSquarePlus")
export const Mic = createAppIcon(Mic01Icon, "Mic")
export const Mic2 = createAppIcon(Mic02Icon, "Mic2")
export const Minimize2 = createAppIcon(Minimize02Icon, "Minimize2")
export const MinusCircle = createAppIcon(MinusSignCircleIcon, "MinusCircle")
export const Monitor = createAppIcon(ComputerIcon, "Monitor")
export const Moon = createAppIcon(Moon02Icon, "Moon")
export const MoreHorizontal = createAppIcon(MoreHorizontalIcon, "MoreHorizontal")
export const Music2 = createAppIcon(MusicNote03Icon, "Music2")
export const OctagonXIcon = createAppIcon(CancelCircleIcon, "OctagonXIcon")
export const Palette = createAppIcon(PaintBoardIcon, "Palette")
export const PanelLeft = createAppIcon(SidebarLeftIcon, "PanelLeft")
export const PanelRight = createAppIcon(SidebarRightIcon, "PanelRight")
export const Paperclip = createAppIcon(Attachment01Icon, "Paperclip")
export const Pause = createAppIcon(PauseIcon, "Pause")
export const Pencil = createAppIcon(PencilEdit02Icon, "Pencil")
export const Play = createAppIcon(PlayIcon, "Play")
export const Plus = createAppIcon(PlusSignIcon, "Plus")
export const Quote = createAppIcon(QuoteDownIcon, "Quote")
export const RefreshCw = createAppIcon(RefreshIcon, "RefreshCw")
export const RotateCcw = createAppIcon(RotateCcwIcon, "RotateCcw")
export const Save = createAppIcon(FloppyDiskIcon, "Save")
export const Scan = createAppIcon(ScanIcon, "Scan")
export const Search = createAppIcon(Search01Icon, "Search")
export const Settings = createAppIcon(Settings01Icon, "Settings")
export const SlidersHorizontal = createAppIcon(SlidersHorizontalIcon, "SlidersHorizontal")
export const Sparkles = createAppIcon(SparklesIcon, "Sparkles")
export const Square = createAppIcon(StopIcon, "Square")
export const Sun = createAppIcon(Sun03Icon, "Sun")
export const ThumbsDown = createAppIcon(ThumbsDownIcon, "ThumbsDown")
export const ThumbsUp = createAppIcon(ThumbsUpIcon, "ThumbsUp")
export const Trash2 = createAppIcon(Delete02Icon, "Trash2")
export const TriangleAlert = createAppIcon(Alert02Icon, "TriangleAlert")
export const TriangleAlertIcon = createAppIcon(Alert02Icon, "TriangleAlertIcon")
export const Type = createAppIcon(TextIcon, "Type")
export const Undo2 = createAppIcon(Undo02Icon, "Undo2")
export const Upload = createAppIcon(Upload04Icon, "Upload")
export const User = createAppIcon(UserIcon, "User")
export const Video = createAppIcon(Video01Icon, "Video")
export const Volume2 = createAppIcon(VolumeHighIcon, "Volume2")
export const VolumeX = createAppIcon(VolumeMute02Icon, "VolumeX")
export const Wand2 = createAppIcon(MagicWand01Icon, "Wand2")
export const Workflow = createAppIcon(WorkflowSquare10Icon, "Workflow")
export const X = createAppIcon(Cancel01Icon, "X")
export const Zap = createAppIcon(FlashIcon, "Zap")
export const ZoomIn = createAppIcon(ZoomInIcon, "ZoomIn")
export const ZoomOut = createAppIcon(ZoomOutIcon, "ZoomOut")

import Foundation
import PDFKit
import Vision
import AppKit

func fail(_ message: String, _ code: Int32 = 2) -> Never {
    FileHandle.standardError.write((message + "\n").data(using: .utf8)!)
    exit(code)
}

guard CommandLine.arguments.count >= 4 else {
    fail("usage: macos_vision_ocr <pdf> <fast|accurate> <all|1,2,3>")
}
let pdfPath = CommandLine.arguments[1]
let mode = CommandLine.arguments[2].lowercased()
let pagesArg = CommandLine.arguments[3]

guard let document = PDFDocument(url: URL(fileURLWithPath: pdfPath)) else {
    fail("could not open PDF")
}

var wanted = Set<Int>()
if pagesArg == "all" {
    for i in 1...max(1, document.pageCount) { wanted.insert(i) }
} else {
    for token in pagesArg.split(separator: ",") {
        if let n = Int(token), n >= 1, n <= document.pageCount { wanted.insert(n) }
    }
}

let recognition: VNRequestTextRecognitionLevel = (mode == "accurate") ? .accurate : .fast
let targetWidth: CGFloat = (mode == "accurate") ? 2200 : 1300
var result: [String:String] = [:]

for pageNo in wanted.sorted() {
    autoreleasepool {
        guard let page = document.page(at: pageNo - 1) else {
            result[String(pageNo)] = ""
            return
        }
        let bounds = page.bounds(for: .mediaBox)
        let ratio = bounds.height > 0 ? bounds.width / bounds.height : 0.75
        let targetSize = NSSize(width: targetWidth, height: max(1000, targetWidth / max(0.2, ratio)))
        let image = page.thumbnail(of: targetSize, for: .mediaBox)
        var rect = NSRect(origin: .zero, size: image.size)
        guard let cgImage = image.cgImage(forProposedRect: &rect, context: nil, hints: nil) else {
            result[String(pageNo)] = ""
            return
        }

        let request = VNRecognizeTextRequest()
        request.recognitionLevel = recognition
        request.usesLanguageCorrection = true
        request.minimumTextHeight = (mode == "accurate") ? 0.006 : 0.008

        do {
            let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
            try handler.perform([request])
            let observations = request.results ?? []
            let lines = observations.compactMap { $0.topCandidates(1).first?.string }
            result[String(pageNo)] = lines.joined(separator: "\n")
        } catch {
            result[String(pageNo)] = ""
        }
    }
}

do {
    let data = try JSONSerialization.data(withJSONObject: result, options: [])
    FileHandle.standardOutput.write(data)
} catch {
    fail("could not encode OCR result")
}

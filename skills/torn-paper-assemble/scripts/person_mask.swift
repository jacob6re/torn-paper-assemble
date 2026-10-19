import Foundation
import Vision
import CoreImage
import ImageIO
import UniformTypeIdentifiers

// Output stays in source pixel coordinates. All visible people form one foreground piece.
do {
    guard CommandLine.arguments.count == 3 else {
        throw NSError(domain: "Usage: person_mask.swift frame.png mask.png", code: 1)
    }
    guard #available(macOS 14.0, *) else {
        throw NSError(domain: "Automatic person matting requires macOS 14+; supply --person-mask", code: 1)
    }
    let handler = VNImageRequestHandler(url: URL(fileURLWithPath: CommandLine.arguments[1]), options: [:])
    let request = VNGeneratePersonInstanceMaskRequest()
    try handler.perform([request])
    guard let observation = request.results?.first, !observation.allInstances.isEmpty else {
        throw NSError(domain: "No person detected; inspect the frame and supply a corrected mask", code: 2)
    }
    let buffer = try observation.generateScaledMaskForImage(forInstances: observation.allInstances, from: handler)
    let image = CIImage(cvPixelBuffer: buffer)
    guard let cg = CIContext().createCGImage(image, from: image.extent),
          let destination = CGImageDestinationCreateWithURL(
            URL(fileURLWithPath: CommandLine.arguments[2]) as CFURL,
            UTType.png.identifier as CFString, 1, nil) else {
        throw NSError(domain: "Cannot write person mask", code: 3)
    }
    CGImageDestinationAddImage(destination, cg, nil)
    guard CGImageDestinationFinalize(destination) else {
        throw NSError(domain: "Person mask write failed", code: 4)
    }
    print("Person mask saved (\(observation.allInstances.count) person instance(s))")
} catch {
    fputs("\(error)\n", stderr)
    exit(1)
}

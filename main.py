import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision.transforms import Compose, ToTensor, Normalize
from torchmetrics import SSIM
from SwinVisionTranformer import SwinTransformer
import matplotlib.pyplot as plt
import torch.nn.functional as F
import os
import numpy as np
from dataset.ImageToImageDataset import ImageToImageDataset
import argparse


parser = argparse.ArgumentParser(description='Train a Swin Transformer model for image-to-image translation')
parser.add_argument('--epochs', type=int, default=100, help='Number of epochs to train for')
parser.add_argument('--batch_size', type=int, default=4, help='Batch size for training')
parser.add_argument('--lr', type=float, default=0.001, help='Learning rate for optimizer')
parser.add_argument('--train_path', type=str, default='/path/to/train', help='Path to training data')
parser.add_argument('--val_path', type=str, default='/path/to/val', help='Path to validation data')
parser.add_argument('--test_path', type=str, default='/path/to/test', help='Path to test data')
parser.add_argument('--checkpoint_path', type=str, default='./checkpoints', help='Path to store checkpoints')
args = parser.parse_args()

# Define hyperparameters
epochs = args.epochs
batch_size = args.batch_size
lr = args.lr
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Define the transforms for the input and label images
mean_data = [mean_r, mean_g, mean_b]  # replace with your calculated values
std_data = [std_r, std_g, std_b]  # replace with your calculated values
mean_label = [mean_ch1, mean_ch2, mean_ch3, mean_ch4]  # replace with your calculated values
std_label = [std_ch1, std_ch2, std_ch3, std_ch4]  # replace with your calculated values

input_transform = Compose([
    ToTensor(),
    Normalize(mean=mean_data, std=std_data)
])
label_transform = Compose([
    ToTensor(),
    Normalize(mean=mean_label, std=std_label)
])

# Create instances of the ImageToImageDataset for the training, validation, and test sets
train_dataset = ImageToImageDataset(args.train_path, input_transform=input_transform, label_transform=label_transform)
val_dataset = ImageToImageDataset(args.val_path, input_transform=input_transform, label_transform=label_transform)
test_dataset = ImageToImageDataset(args.test_path, input_transform=input_transform, label_transform=label_transform)

# Create instances of the DataLoader for the training, validation, and test sets
train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)


# Initialize the model, optimizer, and loss function
model = SwinTransformer().to(device)
optimizer = optim.Adam(model.parameters(), lr=lr)
criterion = nn.MSELoss()

# Initialize SSIM metric
ssim = SSIM(data_range=1.0, kernel_size=11, kernel_sigma=1.5, reduction='none', convert_to_greyscale=False)

# Initialize variables for storing training information
losses = []
ssim_values = []
avg_ssim_values = []
pearson_corr_values = []
psnr_values = []

# Initialize variables for storing validation information
val_losses = []
val_ssim_values = []
val_avg_ssim_values = []
val_pearson_corr_values = []
val_psnr_values = []

best_loss = float("inf")
best_ssim = 0.0

# Initialize the scheduler
scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

# Training loop
for epoch in range(epochs):
    scheduler.step()
    model.train()
    epoch_loss = 0.0
    epoch_ssim = []
    epoch_pr = []
    epoch_psnr = []

    for i, (source, target) in enumerate(train_loader):
        source, target = source.to(device), target.to(device)

        optimizer.zero_grad()

        output = model(source)
        loss = criterion(output, target)
        loss.backward()
        optimizer.step()

        epoch_loss += loss.item()

        # Calculate SSIM
        ssim_val = ssim(output, target)
        epoch_ssim.append(ssim_val.cpu().numpy())


        # Calculate mean squared error (MSE) and mean absolute error (MAE) between the output and target tensors
        mse_loss = F.mse_loss(output, target)
        mae_loss = F.l1_loss(output, target)

        # Calculate Pearson correlation coefficient
        corr_coef = 1.0 - (2.0 * mae_loss) / (mse_loss + torch.mean(target ** 2))
        epoch_pr.append(corr_coef.cpu().numpy())

        # Calculate peak signal-to-noise ratio (PSNR)
        max_val = 1.0
        psnr = 20 * torch.log10(max_val / torch.sqrt(mse_loss))
        epoch_psnr.append(psnr.cpu().numpy())


    epoch_loss /= len(train_loader)
    epoch_ssim = np.mean(epoch_ssim, axis=0)
    avg_ssim = np.mean(epoch_ssim)
    epoch_pr = np.mean(epoch_pr)
    epoch_psnr = np.mean(epoch_psnr)

    losses.append(epoch_loss)
    ssim_values.append(epoch_ssim)
    avg_ssim_values.append(avg_ssim)
    pearson_corr_values.append(epoch_pr)
    psnr_values.append(epoch_psnr)

    #validation loop
    model.eval()
    val_loss = 0.0
    val_ssim = []
    val_pr = []
    val_psnr = []

    with torch.no_grad():
        for i, (source, target) in enumerate(val_loader):
            source, target = source.to(device), target.to(device)

            output = model(source)
            loss = criterion(output, target)
            val_loss += loss.item()

            # Calculate SSIM
            ssim_val = ssim(output, target)
            val_ssim.append(ssim_val.cpu().numpy())

            # Calculate mean squared error (MSE) and mean absolute error (MAE) between the output and target tensors
            mse_loss = F.mse_loss(output, target)
            mae_loss = F.l1_loss(output, target)

            # Calculate Pearson correlation coefficient
            corr_coef = 1.0 - (2.0 * mae_loss) / (mse_loss + torch.mean(target ** 2))
            val_pr.append(corr_coef.cpu().numpy())

            # Calculate peak signal-to-noise ratio (PSNR)
            max_val = 1.0
            psnr = 20 * torch.log10(max_val / torch.sqrt(mse_loss))
            val_psnr.append(psnr.cpu().numpy())

        val_loss /= len(val_loader)
        val_ssim = np.mean(val_ssim, axis=0)
        avg_val_ssim = np.mean(val_ssim)
        val_pr = np.mean(val_pr)
        val_psnr = np.mean(val_psnr)

        val_losses.append(val_losses)
        ssim_values.append(epoch_ssim)
        avg_ssim_values.append(avg_ssim)
        pearson_corr_values.append(epoch_pr)
        psnr_values.append(epoch_psnr)


    print(f"Epoch: {epoch + 1}/{epochs}, Training_Loss: {epoch_loss}, Training_SSIM: {avg_ssim}, Training_Pearson Correlation: {epoch_pr}, Training_PSNR: {epoch_psnr}")
    print(f"Epoch: {epoch + 1}/{epochs}, Validation_Loss: {val_loss}, Validation_SSIM: {val_ssim}, Validation_Pearson Correlation: {val_pr}, Validation_PSNR: {val_psnr}")

    # Save checkpoint every 10 epochs
    if (epoch + 1) % 10 == 0:
        checkpoint_filename = os.path.join(args.checkpoint_path, f"checkpoint_epoch_{epoch + 1}.pth")
        torch.save(model.state_dict(), checkpoint_filename)

    # Save the best loss
    if epoch_loss < best_loss:
        best_loss = epoch_loss
        best_loss_checkpoint = os.path.join(args.checkpoint_path, "best_loss_checkpoint.pth")
        torch.save(model.state_dict(), best_loss_checkpoint)

    # Save the best SSIM
    if avg_val_ssim > best_ssim:
        best_ssim = avg_ssim
        best_ssim_checkpoint = os.path.join(args.checkpoint_path, "best_ssim_checkpoint.pth")
        torch.save(model.state_dict(), best_ssim_checkpoint)


    #plot curves
    # Store loss and SSIM curves
    if (epoch + 1) % 10 == 0:
        fig, ax = plt.subplots(1, 3, figsize=(12, 6))
        ax[0].plot(losses)
        ax[0].set_title("Loss")
        ax[0].set_xlabel("Epoch")
        ax[0].set_ylabel("MSE Loss")

        ax[1].plot(ssim_values)
        ax[1].plot(avg_ssim_values)
        ax[1].set_title("Training_SSIM")
        ax[1].set_xlabel("Epoch")
        ax[1].set_ylabel("SSIM")
        # Add labels for each channel
        ax[1].legend(['Channel 1', 'Channel 2', 'Channel 3', 'Channel 4','Avg'])

        ax[2].plot(val_ssim_values)
        ax[2].plot(val_avg_ssim_values)
        ax[2].set_title("Validation_SSIM")
        ax[2].set_xlabel("Epoch")
        ax[2].set_ylabel("SSIM")
        # Add labels for each channel
        ax[2].legend(['Channel 1', 'Channel 2', 'Channel 3', 'Channel 4', 'Avg'])

        fig.savefig(f"loss_ssim_curves_epoch_{epoch + 1}.png")

    # Generate log file
    log_file = open("training_log.txt", "a")
    log_file.write(f"Epoch: {epoch + 1}/{epochs}, Loss: {epoch_loss:.4f}, SSIM: {avg_ssim:.4f}, Pearson Correlation "
                   f"score: {epoch_pr:.4f}, PSNR: {epoch_psnr:.4f},\n")
    log_file.write(f"Epoch: {epoch + 1}/{epochs}, Val_Loss: {val_loss:.4f}, Val_SSIM: {avg_val_ssim:.4f}, Val_Pearson Correlation "
                   f"score: {val_pr:.4f}, PSNR: {val_psnr:.4f},\n")
    log_file.close()



